import json
from unittest.mock import MagicMock, patch
import pytest
from orchestrator.agents.base import BaseAgent


class DummyAgent(BaseAgent):
    node_name = "DUMMY"

    def build_prompt(self, state):
        return "hello prompt"

    def parse_output(self, raw):
        data = json.loads(raw)
        if "val" not in data:
            raise ValueError("Missing 'val' field in response")
        return data

    def state_update(self, parsed, state):
        return {"result": parsed["val"]}


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_base_agent_success(mock_client):
    mock_resp = MagicMock()
    mock_resp.text = '{"val": 42}'
    mock_resp.usage_metadata.prompt_token_count = 100
    mock_resp.usage_metadata.candidates_token_count = 50
    mock_client.return_value.models.generate_content.return_value = mock_resp

    agent = DummyAgent()
    res = agent({"workflow_id": "wf-1"})

    assert res["result"] == 42
    assert res["current_node"] == "DUMMY"
    assert len(res["agent_history"]) == 1
    assert res["agent_history"][0]["status"] == "success"
    assert len(res["trace_log"]) == 1
    assert res["trace_log"][0]["status"] == "success"
    assert res["trace_log"][0]["input_tokens"] == 100
    assert res["trace_log"][0]["output_tokens"] == 50
    assert res["trace_log"][0]["cost_usd"] > 0


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_base_agent_retry_and_recover(mock_client):
    # Attempt 0 returns bad JSON, Attempt 1 returns valid schema
    bad_resp = MagicMock()
    bad_resp.text = "invalid json {{"
    bad_resp.usage_metadata.prompt_token_count = 10
    bad_resp.usage_metadata.candidates_token_count = 5

    good_resp = MagicMock()
    good_resp.text = '{"val": 99}'
    good_resp.usage_metadata.prompt_token_count = 20
    good_resp.usage_metadata.candidates_token_count = 10

    mock_client.return_value.models.generate_content.side_effect = [bad_resp, good_resp]

    agent = DummyAgent()
    res = agent({"workflow_id": "wf-2"})

    assert res["result"] == 99
    assert mock_client.return_value.models.generate_content.call_count == 2
    assert res["trace_log"][0]["status"] == "success"


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"})
@patch("google.genai.Client")
def test_base_agent_fail_fast(mock_client):
    # All attempts return invalid payload
    bad_resp = MagicMock()
    bad_resp.text = '{"other_key": 123}'  # triggers ValueError in parse_output
    bad_resp.usage_metadata.prompt_token_count = 10
    bad_resp.usage_metadata.candidates_token_count = 5
    mock_client.return_value.models.generate_content.return_value = bad_resp

    agent = DummyAgent()
    agent.max_json_retries = 2

    with pytest.raises(RuntimeError, match="failed to return a valid schema"):
        agent({"workflow_id": "wf-3"})

    # Initial attempt + 2 retries = 3 attempts total
    assert mock_client.return_value.models.generate_content.call_count == 3
