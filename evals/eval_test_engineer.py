import json
from unittest.mock import MagicMock, patch
from orchestrator.agents.test_engineer import TestEngineerAgent


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_test_engineer_eval(mock_client):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "test_file_path": "tests/test_cart.py",
        "test_file_content": "import pytest\ndef test_coupon(): assert True"
    })
    mock_resp.usage_metadata.prompt_token_count = 40
    mock_resp.usage_metadata.candidates_token_count = 40
    mock_client.return_value.models.generate_content.return_value = mock_resp

    mock_sandbox = MagicMock()
    mock_sandbox.run.return_value.success = True
    mock_sandbox.run.return_value.stdout = "def test_old(): pass"

    te = TestEngineerAgent(mock_sandbox)
    state = {
        "workflow_id": "12345678",
        "selected_task": {"id": "TASK-001", "title": "Coupon", "description": "Add coupon"},
        "design_proposal": {"design_rationale": "Clean logic"},
        "acceptance_criteria": ["Apply 10%"],
        "repo_path": "/workspace/runs/test",
    }
    out = te(state)
    assert out["current_node"] == "TEST_WRITING"
    assert mock_sandbox.safe_write_file.called
