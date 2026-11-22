import json
from unittest.mock import MagicMock, patch
import pytest
from orchestrator.agents.analyst import AnalystAgent


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_analyst_evaluation(mock_client):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "acceptance_criteria": ["Apply 10% on SAVE10", "Raise ValueError on invalid code"],
        "tasks": [{"id": "TASK-001", "title": "Discount Coupon", "description": "Implement coupon", "priority": 1}]
    })
    mock_resp.usage_metadata.prompt_token_count = 50
    mock_resp.usage_metadata.candidates_token_count = 50
    mock_client.return_value.models.generate_content.return_value = mock_resp

    mock_sandbox = MagicMock()
    mock_sandbox.run.return_value.success = True
    mock_sandbox.run.return_value.stdout = "cart/services.py"

    analyst = AnalystAgent(mock_sandbox)
    state = {"requirement": "Add discount coupon", "repo_path": "/fake"}
    out = analyst(state)

    assert len(out["acceptance_criteria"]) >= 2
    assert out["tasks"][0]["priority"] == 1
    assert out["current_node"] == "ANALYSIS"
    assert len(out["agent_history"]) == 1
    assert len(out["trace_log"]) == 1


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_analyst_schema_validation_rejection(mock_client):
    # Missing priority in task -> parse_output assertion error -> triggers retry
    bad_resp = MagicMock()
    bad_resp.text = json.dumps({
        "acceptance_criteria": ["Criterion 1", "Criterion 2"],
        "tasks": [{"id": "TASK-001", "title": "T1", "description": "D1"}]  # missing priority
    })
    bad_resp.usage_metadata.prompt_token_count = 10
    bad_resp.usage_metadata.candidates_token_count = 10

    good_resp = MagicMock()
    good_resp.text = json.dumps({
        "acceptance_criteria": ["Criterion 1", "Criterion 2"],
        "tasks": [{"id": "TASK-001", "title": "T1", "description": "D1", "priority": 1}]
    })
    good_resp.usage_metadata.prompt_token_count = 15
    good_resp.usage_metadata.candidates_token_count = 15

    mock_client.return_value.models.generate_content.side_effect = [bad_resp, good_resp]

    mock_sandbox = MagicMock()
    mock_sandbox.run.return_value.success = True
    mock_sandbox.run.return_value.stdout = ""

    analyst = AnalystAgent(mock_sandbox)
    state = {"requirement": "Test requirement", "repo_path": "/fake"}
    out = analyst(state)

    assert out["tasks"][0]["priority"] == 1
    assert mock_client.return_value.models.generate_content.call_count == 2
