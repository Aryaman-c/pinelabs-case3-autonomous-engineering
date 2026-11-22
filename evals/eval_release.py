import json
from unittest.mock import MagicMock, patch
from orchestrator.agents.release import ReleaseAgent


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_release_eval(mock_client):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "known_risks": ["In-memory coupon store resets on app restart"],
        "recommendation": "APPROVE"
    })
    mock_resp.usage_metadata.prompt_token_count = 35
    mock_resp.usage_metadata.candidates_token_count = 35
    mock_client.return_value.models.generate_content.return_value = mock_resp

    rel = ReleaseAgent()
    state = {
        "requirement": "Discount coupon",
        "selected_task": {"id": "TASK-001"},
        "design_proposal": {},
        "code_change": {},
        "test_report": {"passed": 2, "failed": 0},
        "security_report": {"critical_block": False},
    }
    out = rel(state)
    assert out["evidence_package"]["recommendation"] == "APPROVE"
    assert len(out["evidence_package"]["known_risks"]) == 1
    assert out["current_node"] == "RELEASE_PREP"
