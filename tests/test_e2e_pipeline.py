import json
from unittest.mock import MagicMock, patch
import pytest
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.graph import build_graph
from orchestrator.state import WorkflowState


def test_complete_e2e_pipeline_happy_path():
    """
    Simulates the entire autonomous pipeline from requirement intake through
    ANALYSIS -> TASK_SELECT -> ARCHITECTURE -> TEST_WRITING -> DEVELOPMENT ->
    QA_CHECK -> LINT_CHECK -> SECURITY_CHECK -> RELEASE_PREP ->
    HUMAN_REVIEW (interrupt) -> approval -> MERGE_TAG.
    """
    mock_sandbox = MagicMock()
    mock_sandbox.run.return_value = MagicMock(success=True, stdout="")
    mock_sandbox.run_checked.return_value = MagicMock(success=True, stdout="")
    mock_sandbox.git_diff_files.return_value = ["cart/services.py"]

    # 1. Seed initial state
    initial_state: WorkflowState = {
        "workflow_id": "wf-e2e-001",
        "requirement": "Add discount coupon SAVE10 to cart microservice",
        "repo_path": "/workspace/runs/wf-e2e-001",
        "acceptance_criteria": None,
        "tasks": None,
        "selected_task": None,
        "design_proposal": None,
        "code_change": None,
        "test_report": None,
        "security_report": None,
        "evidence_package": None,
        "retry_counts": {},
        "current_node": "INTAKE",
        "human_decision": None,
        "agent_history": [],
        "trace_log": [],
    }

    config = {"configurable": {"thread_id": "thread-e2e-1"}}

    # Mock responses for all LLM-driven agents
    analyst_resp = MagicMock(
        text=json.dumps({
            "acceptance_criteria": ["Apply 10% on SAVE10", "Raise ValueError on invalid code"],
            "tasks": [{"id": "TASK-001", "title": "Discount Coupon", "description": "Implement coupon", "priority": 1}],
        }),
        usage_metadata=MagicMock(prompt_token_count=50, candidates_token_count=50),
    )
    architect_resp = MagicMock(
        text=json.dumps({
            "impacted_components": ["cart"],
            "design_rationale": "Add coupon logic to cart/services.py and cart/models.py",
            "file_changes": [
                {"file": "cart/services.py", "action": "modify", "description": "Add apply_discount"},
            ],
            "constraints": ["Do not touch payments/"],
        }),
        usage_metadata=MagicMock(prompt_token_count=50, candidates_token_count=50),
    )
    test_eng_resp = MagicMock(
        text=json.dumps({
            "test_file_path": "tests/test_cart.py",
            "test_file_content": "def test_coupon(): assert True",
        }),
        usage_metadata=MagicMock(prompt_token_count=40, candidates_token_count=40),
    )
    developer_resp = MagicMock(
        text=json.dumps({
            "files": [{"path": "cart/services.py", "content": "# coupon implementation"}],
            "implementation_notes": "Added discount logic",
        }),
        usage_metadata=MagicMock(prompt_token_count=60, candidates_token_count=60),
    )
    release_resp = MagicMock(
        text=json.dumps({
            "known_risks": ["In-memory coupon store resets on restart"],
            "recommendation": "APPROVE",
        }),
        usage_metadata=MagicMock(prompt_token_count=30, candidates_token_count=30),
    )

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}), \
         patch("google.genai.Client") as mock_client_cls, \
         patch("orchestrator.agents.architect.retrieve_relevant_learnings_sync", return_value=[]), \
         patch("orchestrator.agents.developer.retrieve_relevant_learnings_sync", return_value=[]), \
         patch("subprocess.run") as mock_pip_audit:

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            analyst_resp,    # Analyst
            architect_resp,  # Architect
            test_eng_resp,   # Test Engineer
            developer_resp,  # Developer
            release_resp,    # Release Agent
        ]

        # QA mock output: passed 3, failed 0
        mock_sandbox.run.side_effect = [
            MagicMock(success=True, stdout="cart/services.py\n"),                                              # Analyst find py
            MagicMock(success=True, stdout="def test_old(): pass\n"),                                         # TestEng cat
            MagicMock(success=True, stdout=""),                                                               # TestEng branch -D
            MagicMock(success=True, stdout=""),                                                               # TestEng git add
            MagicMock(success=True, stdout=""),                                                               # TestEng git commit
            MagicMock(success=True, stdout="def get_total(): pass\n"),                                        # Dev cat
            MagicMock(success=True, stdout=""),                                                               # Dev git add
            MagicMock(success=True, stdout=""),                                                               # Dev git commit
            MagicMock(success=True, stdout=""),                                                               # QA pytest
            MagicMock(success=True, stdout=json.dumps({"summary": {"passed": 3, "failed": 0}, "tests": []})), # QA cat report
            MagicMock(success=True, stdout="All checks passed"),                                              # Lint ruff
            MagicMock(success=True, stdout=json.dumps({"results": []})),                                      # Sec bandit
            MagicMock(success=True, stdout="pytest==8.3.3\n"),                                                # Sec cat reqs
        ]

        mock_pip_audit.return_value = MagicMock(stdout=json.dumps({"dependencies": []}), returncode=0)

        checkpointer = MemorySaver()
        graph = build_graph(mock_sandbox, checkpointer)

        # 2. Run graph up to the first checkpoint
        events = list(graph.stream(initial_state, config=config))
        assert len(events) > 0

        # Verify pause at HUMAN_REVIEW
        state_after_pause = graph.get_state(config)
        assert state_after_pause.next == ("HUMAN_REVIEW",)
        assert state_after_pause.values["evidence_package"]["recommendation"] == "APPROVE"
        assert state_after_pause.values["test_report"]["passed"] == 3
        assert state_after_pause.values["security_report"]["critical_block"] is False

        # 3. Human Intervention: Approve & Merge
        graph.update_state(config, {"human_decision": "approve"})
        resume_events = list(graph.stream(None, config=config))
        assert len(resume_events) > 0

        final_state = graph.get_state(config)
        assert final_state.next == ()  # Reached END
        assert final_state.values["current_node"] == "MERGE_TAG"
        history = final_state.values["agent_history"]
        assert any("git merge --no-ff" in h.get("merge_command", "") for h in history)
