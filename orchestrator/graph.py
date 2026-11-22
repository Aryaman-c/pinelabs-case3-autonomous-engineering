import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from orchestrator.state import WorkflowState
from orchestrator.agents.analyst import AnalystAgent
from orchestrator.agents.architect import ArchitectAgent
from orchestrator.agents.test_engineer import TestEngineerAgent
from orchestrator.agents.developer import DeveloperAgent
from orchestrator.agents.qa import QAAgent
from orchestrator.agents.lint import LintAgent
from orchestrator.agents.security import SecurityAgent
from orchestrator.agents.release import ReleaseAgent
from orchestrator.tools.sandbox import Sandbox

MAX_RETRIES = int(os.environ.get("MAX_DEVELOPER_RETRIES", "3"))


def build_graph(sandbox: Sandbox, checkpointer: BaseCheckpointSaver):
    analyst = AnalystAgent(sandbox)
    architect = ArchitectAgent(sandbox)
    test_engineer = TestEngineerAgent(sandbox)
    developer = DeveloperAgent(sandbox)
    qa = QAAgent(sandbox)
    lint = LintAgent(sandbox)
    security = SecurityAgent(sandbox)
    release = ReleaseAgent()

    def route_after_dev(state: WorkflowState) -> str:
        if state.get("code_change", {}).get("conflict_detected"):
            return "CONFLICT_PAUSE"
        return "PARALLEL_GATES"

    def route_after_gates(state: WorkflowState) -> str:
        test_rep = state.get("test_report") or {}
        sec_rep = state.get("security_report") or {}
        retries = state.get("retry_counts", {}).get("developer", 0)

        if sec_rep.get("critical_block"):
            return "SECURITY_HOLD"

        if not test_rep.get("success", False):
            if retries < MAX_RETRIES:
                return "DEVELOPMENT"
            return "RELEASE_PREP"

        return "RELEASE_PREP"

    def route_after_conflict(state: WorkflowState) -> str:
        return "ARCHITECTURE" if state.get("human_decision") == "re_design" else "RELEASE_PREP"

    def route_after_sec_hold(state: WorkflowState) -> str:
        return "DEVELOPMENT" if state.get("human_decision") == "re_develop" else "RELEASE_PREP"

    def route_after_review(state: WorkflowState) -> str:
        dec = state.get("human_decision")
        if dec == "approve":
            return "MERGE_TAG"
        if dec == "re_design":
            return "ARCHITECTURE"
        if dec == "re_develop":
            return "DEVELOPMENT"
        return END

    wf = StateGraph(WorkflowState)

    # Core Nodes
    wf.add_node("ANALYSIS", analyst)
    wf.add_node("TASK_SELECT", lambda s: {
        "selected_task": min(s["tasks"], key=lambda t: t["priority"]),
        "current_node": "TASK_SELECT",
        "retry_counts": {"developer": 0}
    })
    wf.add_node("ARCHITECTURE", architect)
    wf.add_node("TEST_WRITING", test_engineer)
    wf.add_node("DEVELOPMENT", developer)

    # Parallel Gates
    wf.add_node("QA_CHECK", qa)
    wf.add_node("LINT_CHECK", lint)
    wf.add_node("SECURITY_CHECK", security)
    wf.add_node("RELEASE_PREP", release)

    # Gate & Terminal Nodes
    wf.add_node("CONFLICT_PAUSE", lambda s: {"current_node": "CONFLICT_PAUSE"})
    wf.add_node("SECURITY_HOLD", lambda s: {"current_node": "SECURITY_HOLD"})
    wf.add_node("HUMAN_REVIEW", lambda s: {"current_node": "HUMAN_REVIEW"})
    wf.add_node("MERGE_TAG", lambda s: {
        "current_node": "MERGE_TAG",
        "agent_history": [{
            "node": "MERGE_TAG",
            "merge_command": f"git checkout main && git merge --no-ff {s['code_change']['branch_name']} && git push origin main"
        }]
    })

    # Flow Wiring
    wf.set_entry_point("ANALYSIS")
    wf.add_edge("ANALYSIS", "TASK_SELECT")
    wf.add_edge("TASK_SELECT", "ARCHITECTURE")
    wf.add_edge("ARCHITECTURE", "TEST_WRITING")
    wf.add_edge("TEST_WRITING", "DEVELOPMENT")

    wf.add_conditional_edges("DEVELOPMENT", route_after_dev, {
        "PARALLEL_GATES": "QA_CHECK",
        "CONFLICT_PAUSE": "CONFLICT_PAUSE"
    })

    # Parallel Execution to Quality Gates
    wf.add_edge("QA_CHECK", "LINT_CHECK")
    wf.add_edge("LINT_CHECK", "SECURITY_CHECK")

    wf.add_conditional_edges("SECURITY_CHECK", route_after_gates, {
        "SECURITY_HOLD": "SECURITY_HOLD",
        "DEVELOPMENT": "DEVELOPMENT",
        "RELEASE_PREP": "RELEASE_PREP",
    })

    wf.add_edge("RELEASE_PREP", "HUMAN_REVIEW")

    wf.add_conditional_edges("CONFLICT_PAUSE", route_after_conflict, {
        "ARCHITECTURE": "ARCHITECTURE",
        "RELEASE_PREP": "RELEASE_PREP"
    })
    wf.add_conditional_edges("SECURITY_HOLD", route_after_sec_hold, {
        "DEVELOPMENT": "DEVELOPMENT",
        "RELEASE_PREP": "RELEASE_PREP"
    })
    wf.add_conditional_edges("HUMAN_REVIEW", route_after_review, {
        "MERGE_TAG": "MERGE_TAG",
        "ARCHITECTURE": "ARCHITECTURE",
        "DEVELOPMENT": "DEVELOPMENT",
        END: END
    })
    wf.add_edge("MERGE_TAG", END)

    return wf.compile(
        checkpointer=checkpointer,
        interrupt_before=["CONFLICT_PAUSE", "SECURITY_HOLD", "HUMAN_REVIEW"],
    )
