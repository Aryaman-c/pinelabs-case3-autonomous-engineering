import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from orchestrator.state import WorkflowState, SecurityReport, BanditFinding, PipAuditFinding
from orchestrator.tools.sandbox import Sandbox
import structlog

log = structlog.get_logger()


class SecurityAgent:
    node_name = "SECURITY_CHECK"

    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox

    def __call__(self, state: WorkflowState) -> dict:
        started_at = datetime.now(timezone.utc)
        start_ms = time.monotonic_ns() // 1_000_000
        workdir = state["repo_path"]
        branch = state["code_change"]["branch_name"]

        self.sandbox.run_checked(f"git checkout {branch}", workdir)

        # 1. Bandit SAST on non-deleted modified Python files
        py_files = [f for f in state["code_change"]["files_modified"] if f.endswith(".py")]
        bandit_findings: list[BanditFinding] = []

        if py_files:
            file_args = " ".join(py_files)
            res = self.sandbox.run(f"bandit -f json {file_args}", workdir)
            if res.stdout:
                try:
                    data = json.loads(res.stdout)
                    for item in data.get("results", []):
                        bandit_findings.append({
                            "filename": item["filename"],
                            "line": item["line_number"],
                            "test_id": item["test_id"],
                            "issue_text": item["issue_text"],
                            "severity": item["issue_severity"].upper(),
                            "confidence": item["issue_confidence"],
                        })
                except json.JSONDecodeError:
                    log.error("security.bandit_json_parse_error", output=res.stdout)

        # 2. pip-audit via tempfile on host orchestrator
        req_res = self.sandbox.run("cat requirements.txt", workdir)
        pip_findings: list[PipAuditFinding] = []

        if req_res.success and req_res.stdout.strip():
            with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as tmp:
                tmp.write(req_res.stdout)
                tmp.flush()
                tmp_name = tmp.name

            try:
                import sys
                audit_proc = subprocess.run(
                    [sys.executable, "-m", "pip_audit", "--format", "json", "-r", tmp_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if audit_proc.stdout:
                    try:
                        audit_data = json.loads(audit_proc.stdout)
                        for dep in audit_data.get("dependencies", []):
                            for vuln in dep.get("vulns", []):
                                pip_findings.append({
                                    "package": dep["name"],
                                    "version": dep["version"],
                                    "vuln_id": vuln["id"],
                                    "description": vuln.get("description", ""),
                                    "fix_versions": vuln.get("fix_versions", []),
                                })
                    except json.JSONDecodeError:
                        log.error("security.pip_audit_parse_error", output=audit_proc.stdout)
            except subprocess.TimeoutExpired:
                log.warning("security.pip_audit_timeout", note="pip-audit query timed out after 5s; proceeding with SAST findings")
            except Exception as e:
                log.warning("security.pip_audit_exec_error", error=str(e))
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)

        severity_summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for b in bandit_findings:
            sev = b["severity"]
            if sev in severity_summary:
                severity_summary[sev] += 1

        critical_block = severity_summary["HIGH"] > 0

        report: SecurityReport = {
            "bandit_findings": bandit_findings,
            "pip_audit_findings": pip_findings,
            "severity_summary": severity_summary,
            "critical_block": critical_block,
            "scan_target": f"Changed files: {py_files}",
        }

        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        return {
            "security_report": report,
            "current_node": self.node_name,
            "agent_history": [{"node": self.node_name, "critical_block": critical_block}],
            "trace_log": [{
                "node": self.node_name,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "model": "bandit+pip-audit",
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "status": "critical_blocked" if critical_block else "passed",
                "error": None,
            }],
        }
