import json
from unittest.mock import MagicMock, patch
from orchestrator.agents.architect import ArchitectAgent


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
@patch("orchestrator.agents.architect.retrieve_relevant_learnings_sync", return_value=[])
def test_architect_eval(mock_rag, mock_client):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "impacted_components": ["cart"],
        "design_rationale": "Store coupon mapping in models.py and execute discount calculation in services.py",
        "file_changes": [
            {"file": "cart/models.py", "action": "modify", "description": "Add coupon definition"},
            {"file": "cart/services.py", "action": "modify", "description": "Add apply_discount logic"}
        ],
        "constraints": ["Do not touch payments/"]
    })
    mock_resp.usage_metadata.prompt_token_count = 60
    mock_resp.usage_metadata.candidates_token_count = 60
    mock_client.return_value.models.generate_content.return_value = mock_resp

    architect = ArchitectAgent(MagicMock())
    state = {
        "requirement": "Add discount coupon",
        "selected_task": {"id": "TASK-001", "title": "Coupon", "description": "Add discount"},
        "acceptance_criteria": ["10% off"],
    }
    out = architect(state)
    assert len(out["design_proposal"]["file_changes"]) == 2
    assert out["current_node"] == "ARCHITECTURE"
    assert out["human_decision"] is None
