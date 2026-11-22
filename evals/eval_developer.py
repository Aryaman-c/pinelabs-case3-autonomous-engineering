import json
from unittest.mock import MagicMock, patch
from orchestrator.agents.developer import DeveloperAgent


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
@patch("orchestrator.agents.developer.retrieve_relevant_learnings_sync", return_value=[])
def test_developer_eval(mock_rag, mock_client):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "files": [{"path": "cart/services.py", "content": "class CartService: pass"}],
        "implementation_notes": "Implemented service"
    })
    mock_resp.usage_metadata.prompt_token_count = 50
    mock_resp.usage_metadata.candidates_token_count = 50
    mock_client.return_value.models.generate_content.return_value = mock_resp

    mock_sandbox = MagicMock()
    mock_sandbox.run.return_value.success = True
    mock_sandbox.run.return_value.stdout = "def get_total(): pass"
    mock_sandbox.git_diff_files.return_value = ["cart/services.py"]
    mock_sandbox.run_checked.return_value.stdout = "diff --git..."

    dev = DeveloperAgent(mock_sandbox)
    state = {
        "workflow_id": "12345678",
        "requirement": "Add discount coupon",
        "selected_task": {"id": "TASK-001", "title": "Coupon", "description": "Add coupon"},
        "design_proposal": {"design_rationale": "Simple", "file_changes": [{"file": "cart/services.py"}]},
        "repo_path": "/workspace/runs/test",
    }
    out = dev(state)
    assert out["code_change"]["conflict_detected"] is False
    assert out["code_change"]["branch_name"] == "feat/12345678-task-001"
    assert out["retry_counts"]["developer"] == 1
    assert out["human_decision"] is None
