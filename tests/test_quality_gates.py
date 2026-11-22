import json
from unittest.mock import MagicMock, patch
from orchestrator.agents.qa import QAAgent
from orchestrator.agents.lint import LintAgent
from orchestrator.agents.security import SecurityAgent


def test_lint_agent_success():
    mock_sb = MagicMock()
    mock_sb.run.return_value.success = True
    mock_sb.run.return_value.stdout = "All checks passed"

    lint = LintAgent(mock_sb)
    res = lint({"repo_path": "/fake", "code_change": {"files_modified": ["cart/services.py"]}})
    assert res["agent_history"][0]["passed"] is True
    assert res["trace_log"][0]["status"] == "passed"


def test_qa_agent_success():
    mock_sb = MagicMock()
    mock_sb.run.return_value.success = True
    mock_sb.run.return_value.stdout = json.dumps({"summary": {"passed": 3, "failed": 0}, "tests": []})

    qa = QAAgent(mock_sb)
    res = qa({"repo_path": "/fake", "code_change": {"branch_name": "feat/test"}})
    assert res["test_report"]["success"] is True
    assert res["test_report"]["passed"] == 3
    assert res["trace_log"][0]["status"] == "passed"


def test_security_agent_clean():
    mock_sb = MagicMock()
    mock_sb.run_checked.return_value = MagicMock(success=True)
    # bandit clean output
    mock_sb.run.side_effect = [
        MagicMock(success=True, stdout=json.dumps({"results": []})),  # bandit
        MagicMock(success=True, stdout="pytest==8.3.3\n"),            # requirements.txt
    ]

    sec = SecurityAgent(mock_sb)
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(stdout=json.dumps({"dependencies": []}), returncode=0)
        res = sec({
            "repo_path": "/fake",
            "code_change": {"branch_name": "feat/test", "files_modified": ["cart/services.py"]}
        })

    assert res["security_report"]["critical_block"] is False
    assert res["security_report"]["severity_summary"]["HIGH"] == 0
    assert res["trace_log"][0]["status"] == "passed"
