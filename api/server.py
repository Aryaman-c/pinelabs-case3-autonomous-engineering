from dotenv import load_dotenv
load_dotenv(override=True)

import asyncio
import json
import uuid
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from google import genai
try:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
except ImportError:
    from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver

# Force LangGraph checkpointer to use standard direct journal_mode=DELETE instead of WAL
async def _delete_mode_setup(self) -> None:
    async with self.lock:
        if self.is_setup:
            return
        if not self.conn.is_alive():
            await self.conn
        async with self.conn.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            );
            CREATE TABLE IF NOT EXISTS writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            );
            """
        ):
            await self.conn.commit()
        self.is_setup = True

AsyncSqliteSaver.setup = _delete_mode_setup

from orchestrator.graph import build_graph
from orchestrator.tools.sandbox import Sandbox
from orchestrator.state import WorkflowState
from orchestrator.memory.store import record_workflow_learning_sync, init_memory_db_sync
import structlog

log = structlog.get_logger()

_queues: dict[str, asyncio.Queue] = {}
graph = None
sandbox = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph, sandbox
    db_path = os.environ.get("WORKFLOW_DB_PATH", "data/workflows.db")
    if db_path.startswith("/app/") and not os.path.exists("/app"):
        db_path = db_path.replace("/app/", "")
    init_memory_db_sync(db_path)
    sandbox_name = os.environ.get("SANDBOX_CONTAINER_NAME", "autonomous-eng-org-sandbox")
    try:
        sandbox = Sandbox(container_name=sandbox_name, timeout=2)
    except Exception:
        sandbox = None

    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        if sandbox:
            graph = build_graph(sandbox, checkpointer)
        yield


app = FastAPI(title="Autonomous Engineering Org", lifespan=lifespan)
os.makedirs("api/templates", exist_ok=True)
os.makedirs("api/static", exist_ok=True)
templates = Jinja2Templates(directory="api/templates")
app.mount("/static", StaticFiles(directory="api/static"), name="static")


class WorkflowStartRequest(BaseModel):
    requirement: str


class DecisionRequest(BaseModel):
    action: str  # "approve" | "reject" | "re_design" | "re_develop"
    critique: Optional[str] = ""


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.post("/workflow/start")
async def start_flow(body: WorkflowStartRequest):
    global sandbox, graph
    load_dotenv(override=True)
    if not sandbox:
        try:
            sandbox_name = os.environ.get("SANDBOX_CONTAINER_NAME", "autonomous-eng-org-sandbox")
            sandbox = Sandbox(container_name=sandbox_name, timeout=5)
        except Exception:
            sandbox = None

    if not sandbox or not graph:
        raise HTTPException(503, "Sandbox or Graph execution engine is not initialized. Ensure Docker is running.")

    wfid = str(uuid.uuid4())
    _queues[wfid] = asyncio.Queue()
    try:
        sample_repo = "/app/sample-repo" if os.path.exists("/app/sample-repo") else os.path.abspath("sample-repo")
        repo_path = await asyncio.to_thread(sandbox.init_workflow_repo, wfid, sample_repo)
    except Exception as e:
        log.error("workflow.start_failed", error=str(e))
        raise HTTPException(500, f"Failed to initialize sandbox workspace: {e}")

    state: WorkflowState = {
        "workflow_id": wfid,
        "requirement": body.requirement,
        "repo_path": repo_path,
        "acceptance_criteria": None,
        "tasks": None,
        "selected_task": None,
        "design_proposal": None,
        "code_change": None,
        "test_report": None,
        "security_report": None,
        "evidence_package": None,
        "retry_counts": {},
        "current_node": "INTAKE",
        "human_decision": None,
        "agent_history": [],
        "trace_log": [],
    }

    config = {"configurable": {"thread_id": wfid}}
    asyncio.create_task(_execute_graph(wfid, state, config))
    return {"workflow_id": wfid}


async def _execute_graph(wfid: str, state_input: dict, config: dict):
    q = _queues.get(wfid)
    try:
        async for event in graph.astream(state_input, config=config, stream_mode="updates"):
            if q:
                await q.put({"type": "update", "data": event})

        curr_state = await graph.aget_state(config)
        if curr_state and curr_state.next:
            paused_node = curr_state.next[0]
            val = curr_state.values
            if q:
                await q.put({
                    "type": "paused",
                    "next_node": paused_node,
                    "evidence": val.get("evidence_package"),
                    "diff": val.get("code_change", {}).get("diff", ""),
                    "conflict_detail": val.get("code_change", {}).get("conflict_detail", ""),
                    "security_report": val.get("security_report"),
                })
        else:
            merge_cmd = ""
            for h in (curr_state.values.get("agent_history", []) if curr_state else []):
                if "merge_command" in h:
                    merge_cmd = h["merge_command"]

            if q:
                await q.put({
                    "type": "complete",
                    "values": curr_state.values if curr_state else {},
                    "merge_command": merge_cmd,
                })
    except Exception as e:
        if q:
            await q.put({"type": "error", "message": str(e)})


@app.get("/workflow/{wfid}/stream")
async def stream(wfid: str):
    q = _queues.get(wfid)
    if not q:
        raise HTTPException(404, "Workflow queue not found")

    async def sse_gen() -> AsyncGenerator[str, None]:
        while True:
            item = await q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"
            if item.get("type") in ("complete", "paused", "error"):
                break

    return StreamingResponse(sse_gen(), media_type="text/event-stream")


@app.post("/workflow/{wfid}/decision")
async def apply_decision(wfid: str, body: DecisionRequest):
    if not graph:
        raise HTTPException(503, "Graph execution engine is not initialized")

    config = {"configurable": {"thread_id": wfid}}
    curr_state = await graph.aget_state(config)
    vals = curr_state.values if curr_state else {}

    if body.action in ("approve", "reject") and vals:
        req = vals.get("requirement", "")
        design = vals.get("design_proposal", {}).get("design_rationale", "")
        diff = vals.get("code_change", {}).get("diff", "")

        api_key = os.environ.get("GEMINI_API_KEY", "")
        await asyncio.to_thread(
            record_workflow_learning_sync,
            client=genai.Client(api_key=api_key or "DUMMY_KEY"),
            workflow_id=wfid,
            requirement=req,
            design_pattern=design,
            code_diff=diff,
            human_verdict=body.action.upper(),
            human_critique=body.critique or "",
        )

    _queues[wfid] = asyncio.Queue()
    await graph.aupdate_state(config, {"human_decision": body.action})
    asyncio.create_task(_execute_graph(wfid, None, config))
    return {"status": "resumed", "action": body.action}
