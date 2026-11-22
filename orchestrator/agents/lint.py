import time
from datetime import datetime, timezone
from orchestrator.state import WorkflowState
from orchestrator.tools.sandbox import Sandbox


class LintAgent:
    node_name = "LINT_CHECK"

    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox

    def __call__(self, state: WorkflowState) -> dict:
        started_at = datetime.now(timezone.utc)
        start_ms = time.monotonic_ns() // 1_000_000
        workdir = state["repo_path"]

        py_files = [f for f in state.get("code_change", {}).get("files_modified", []) if f.endswith(".py")]
        lint_passed = True
        output = "No Python files to lint"

        if py_files:
            files_arg = " ".join(py_files)
            res = self.sandbox.run(f"ruff check {files_arg}", workdir)
            lint_passed = res.success
            output = res.stdout if not res.success else "Clean: 0 lint errors"

        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        return {
            "agent_history": [{"node": self.node_name, "passed": lint_passed, "output": output}],
            "trace_log": [{
                "node": self.node_name,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "model": "ruff (deterministic)",
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "status": "passed" if lint_passed else "failed",
                "error": None if lint_passed else output[:300],
            }],
        }
