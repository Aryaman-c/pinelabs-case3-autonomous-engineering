import json
import time
from datetime import datetime, timezone
from orchestrator.state import WorkflowState, TestReport
from orchestrator.tools.sandbox import Sandbox


class QAAgent:
    node_name = "QA_CHECK"

    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox

    def __call__(self, state: WorkflowState) -> dict:
        started_at = datetime.now(timezone.utc)
        start_ms = time.monotonic_ns() // 1_000_000
        workdir = state["repo_path"]
        branch = state["code_change"]["branch_name"]

        self.sandbox.run_checked(f"git checkout {branch}", workdir)
        res = self.sandbox.run("pytest tests/ --json-report --json-report-file=/tmp/report.json -v", workdir)
        cat_res = self.sandbox.run("cat /tmp/report.json", workdir)

        passed = failed = 0
        errors = []
        coverage = 0.0

        if cat_res.success and cat_res.stdout.strip():
            try:
                data = json.loads(cat_res.stdout)
                summary = data.get("summary", {})
                passed = summary.get("passed", 0)
                failed = summary.get("failed", 0)
                for t in data.get("tests", []):
                    if t.get("outcome") == "failed":
                        errors.append(f"{t.get('nodeid')}: {t.get('call', {}).get('longrepr', 'Failed')[:300]}")
            except Exception:
                failed = 1
                errors.append(res.stdout[-1000:])
        else:
            failed = 1 if not res.success else 0
            passed = 1 if res.success else 0
            if not res.success:
                errors.append(res.stdout[-1000:])

        success = (failed == 0 and passed > 0)
        report: TestReport = {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "coverage": coverage,
            "raw_output": res.stdout[-2000:],
            "success": success,
        }

        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        return {
            "test_report": report,
            "current_node": self.node_name,
            "agent_history": [{"node": self.node_name, "passed": passed, "failed": failed}],
            "trace_log": [{
                "node": self.node_name,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "model": "pytest (deterministic)",
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "status": "passed" if success else "failed",
                "error": None if success else f"{failed} tests failed",
            }],
        }
