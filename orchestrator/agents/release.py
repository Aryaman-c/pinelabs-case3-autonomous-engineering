import json
import os
from orchestrator.agents.base import BaseAgent
from orchestrator.state import WorkflowState, EvidencePackage


class ReleaseAgent(BaseAgent):
    model = os.environ.get("GEMINI_MODEL_FAST", "gemini-2.0-flash-exp")
    node_name = "RELEASE_PREP"

    def build_prompt(self, state: WorkflowState) -> str:
        test_rep = state.get("test_report") or {}
        sec_rep = state.get("security_report") or {}
        return f"""You are a Release Governance Engineer. Synthesize the verification package.

REQUIREMENT: {state['requirement']}
TESTS: {test_rep.get('passed', 0)} Passed, {test_rep.get('failed', 0)} Failed
SECURITY: Bandit HIGH={sec_rep.get('severity_summary', {}).get('HIGH', 0)}, CriticalBlock={sec_rep.get('critical_block', False)}
DIFF: {state.get('code_change', {}).get('diff', '')[:2000]}

Return ONLY JSON:
{{
  "known_risks": ["string"],
  "recommendation": "APPROVE" | "REJECT" | "APPROVE_WITH_CONDITIONS"
}}
"""

    def parse_output(self, raw: str) -> dict:
        data = json.loads(raw)
        assert data.get("recommendation") in ("APPROVE", "REJECT", "APPROVE_WITH_CONDITIONS")
        assert isinstance(data.get("known_risks"), list)
        return data

    def state_update(self, parsed: dict, state: WorkflowState) -> dict:
        pkg: EvidencePackage = {
            "requirement": state["requirement"],
            "acceptance_criteria": state.get("acceptance_criteria") or [],
            "selected_task": state["selected_task"],
            "design_proposal": state["design_proposal"],
            "code_change": state["code_change"],
            "test_report": state["test_report"],
            "security_report": state["security_report"],
            "known_risks": parsed["known_risks"],
            "recommendation": parsed["recommendation"],
        }
        return {"evidence_package": pkg}

    def get_demo_fallback(self, state: WorkflowState) -> str:
        return json.dumps({
            "known_risks": [
                "Coupon codes are evaluated case-sensitively ('SAVE10' vs 'save10')"
            ],
            "recommendation": "APPROVE"
        })
