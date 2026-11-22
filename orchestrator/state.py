import operator
from typing import Annotated, Any, Optional, TypedDict


class Task(TypedDict):
    id: str
    title: str
    description: str
    priority: int


class FileChange(TypedDict):
    file: str
    action: str  # "modify" | "create" | "delete"
    description: str


class DesignProposal(TypedDict):
    impacted_components: list[str]
    design_rationale: str
    file_changes: list[FileChange]
    constraints: list[str]


class CodeChange(TypedDict):
    branch_name: str
    files_modified: list[str]
    diff: str
    implementation_notes: str
    conflict_detected: bool
    conflict_detail: str


class TestReport(TypedDict):
    passed: int
    failed: int
    errors: list[str]
    coverage: float
    raw_output: str
    success: bool


class BanditFinding(TypedDict):
    filename: str
    line: int
    test_id: str
    issue_text: str
    severity: str
    confidence: str


class PipAuditFinding(TypedDict):
    package: str
    version: str
    vuln_id: str
    description: str
    fix_versions: list[str]


class SecurityReport(TypedDict):
    bandit_findings: list[BanditFinding]
    pip_audit_findings: list[PipAuditFinding]
    severity_summary: dict[str, int]
    critical_block: bool
    scan_target: str


class EvidencePackage(TypedDict):
    requirement: str
    acceptance_criteria: list[str]
    selected_task: Task
    design_proposal: DesignProposal
    code_change: CodeChange
    test_report: TestReport
    security_report: SecurityReport
    known_risks: list[str]
    recommendation: str


class TraceEntry(TypedDict):
    node: str
    started_at: str
    finished_at: str
    duration_ms: int
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: str
    error: Optional[str]


class WorkflowState(TypedDict):
    workflow_id: str
    requirement: str
    repo_path: str

    acceptance_criteria: Optional[list[str]]
    tasks: Optional[list[Task]]
    selected_task: Optional[Task]

    design_proposal: Optional[DesignProposal]
    code_change: Optional[CodeChange]
    test_report: Optional[TestReport]
    security_report: Optional[SecurityReport]
    evidence_package: Optional[EvidencePackage]

    retry_counts: dict[str, int]
    current_node: str
    human_decision: Optional[str]  # "approve" | "reject" | "re_design" | "re_develop"

    # Reducer ensures append-only history and trace across all graph transitions
    agent_history: Annotated[list[dict[str, Any]], operator.add]
    trace_log: Annotated[list[TraceEntry], operator.add]
