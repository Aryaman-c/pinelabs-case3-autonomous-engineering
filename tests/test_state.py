import operator
from typing import get_type_hints
from orchestrator.state import (
    WorkflowState,
    Task,
    FileChange,
    DesignProposal,
    CodeChange,
    TestReport,
    BanditFinding,
    PipAuditFinding,
    SecurityReport,
    EvidencePackage,
    TraceEntry,
)

TestReport.__test__ = False


def test_state_reducers():
    hints = get_type_hints(WorkflowState, include_extras=True)
    
    assert operator.add in hints["agent_history"].__metadata__, "agent_history missing operator.add reducer"
    assert operator.add in hints["trace_log"].__metadata__, "trace_log missing operator.add reducer"


def test_state_keys():
    expected = {
        "workflow_id", "requirement", "repo_path", "acceptance_criteria",
        "tasks", "selected_task", "design_proposal", "code_change",
        "test_report", "security_report", "evidence_package", "retry_counts",
        "current_node", "human_decision", "agent_history", "trace_log"
    }
    assert expected.issubset(set(WorkflowState.__annotations__.keys()))


def test_state_instantiation_and_structure():
    task: Task = {
        "id": "TASK-001",
        "title": "Add discount coupon",
        "description": "Implement SAVE10 coupon",
        "priority": 1,
    }
    fc: FileChange = {
        "file": "cart/services.py",
        "action": "modify",
        "description": "Add coupon logic",
    }
    dp: DesignProposal = {
        "impacted_components": ["cart"],
        "design_rationale": "Add coupon support",
        "file_changes": [fc],
        "constraints": ["Do not touch payments/"],
    }
    cc: CodeChange = {
        "branch_name": "feat/coupon",
        "files_modified": ["cart/services.py"],
        "diff": "+ discount logic",
        "implementation_notes": "Implemented",
        "conflict_detected": False,
        "conflict_detail": "",
    }
    tr: TestReport = {
        "passed": 3,
        "failed": 0,
        "errors": [],
        "coverage": 100.0,
        "raw_output": "3 passed",
        "success": True,
    }
    sr: SecurityReport = {
        "bandit_findings": [],
        "pip_audit_findings": [],
        "severity_summary": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
        "critical_block": False,
        "scan_target": "Changed files",
    }
    ep: EvidencePackage = {
        "requirement": "Add coupon",
        "acceptance_criteria": ["10% discount"],
        "selected_task": task,
        "design_proposal": dp,
        "code_change": cc,
        "test_report": tr,
        "security_report": sr,
        "known_risks": [],
        "recommendation": "APPROVE",
    }
    entry: TraceEntry = {
        "node": "ANALYSIS",
        "started_at": "2026-11-21T00:00:00Z",
        "finished_at": "2026-11-21T00:00:01Z",
        "duration_ms": 1000,
        "model": "gemini-2.0-flash-exp",
        "input_tokens": 10,
        "output_tokens": 10,
        "cost_usd": 0.0001,
        "status": "success",
        "error": None,
    }
    state: WorkflowState = {
        "workflow_id": "wf-12345",
        "requirement": "Add coupon",
        "repo_path": "/workspace/runs/wf-12345",
        "acceptance_criteria": ["10% discount"],
        "tasks": [task],
        "selected_task": task,
        "design_proposal": dp,
        "code_change": cc,
        "test_report": tr,
        "security_report": sr,
        "evidence_package": ep,
        "retry_counts": {"developer": 0},
        "current_node": "INTAKE",
        "human_decision": None,
        "agent_history": [{"node": "INTAKE"}],
        "trace_log": [entry],
    }

    assert state["workflow_id"] == "wf-12345"
    assert len(state["agent_history"]) == 1
    assert len(state["trace_log"]) == 1

    # Simulate reducer accumulation
    new_history = [{"node": "ANALYSIS"}]
    accumulated_history = operator.add(state["agent_history"], new_history)
    assert len(accumulated_history) == 2
    assert accumulated_history[1]["node"] == "ANALYSIS"
