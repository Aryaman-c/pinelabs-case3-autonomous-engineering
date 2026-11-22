import json
import os
from orchestrator.agents.base import BaseAgent
from orchestrator.state import WorkflowState
from orchestrator.tools.sandbox import Sandbox
from orchestrator.memory.store import retrieve_relevant_learnings_sync


class ArchitectAgent(BaseAgent):
    model = os.environ.get("GEMINI_MODEL_SMART", "gemini-2.0-pro-exp")
    node_name = "ARCHITECTURE"

    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox

    def build_prompt(self, state: WorkflowState) -> str:
        task = state["selected_task"]
        criteria = "\n".join(f"- {c}" for c in (state["acceptance_criteria"] or []))

        # RAG self-evolution query
        past_learnings = retrieve_relevant_learnings_sync(
            self.client, state["requirement"], min_score=0.72, top_k=2
        )
        learning_str = ""
        if past_learnings:
            learning_str = "INSTITUTIONAL MEMORY (Past Engineering Reviews):\n"
            for p in past_learnings:
                learning_str += f"- Past Verdict: {p['human_verdict']}\n  Critique: {p['human_critique']}\n"

        return f"""You are a Principal Software Architect.
TASK:
ID: {task['id']} - {task['title']}
{task['description']}

ACCEPTANCE CRITERIA:
{criteria}

{learning_str}

Define the strict, minimal file changes required. Restrict blast radius.
Return ONLY JSON:
{{
  "impacted_components": ["cart"],
  "design_rationale": "string",
  "file_changes": [
    {{
      "file": "cart/services.py",
      "action": "modify",
      "description": "string"
    }},
    {{
      "file": "cart/models.py",
      "action": "modify",
      "description": "string"
    }}
  ],
  "constraints": ["Do not touch payments/", "Do not hardcode constants in services.py"]
}}
"""

    def parse_output(self, raw: str) -> dict:
        data = json.loads(raw)
        assert isinstance(data.get("file_changes"), list) and len(data["file_changes"]) > 0
        for fc in data["file_changes"]:
            assert all(k in fc for k in ("file", "action", "description"))
            assert fc["action"] in ("modify", "create", "delete")
        return data

    def state_update(self, parsed: dict, state: WorkflowState) -> dict:
        return {
            "design_proposal": parsed,
            "human_decision": None,  # Reset stale decision upon re-entry
        }

    def get_demo_fallback(self, state: WorkflowState) -> str:
        past_learnings = retrieve_relevant_learnings_sync(
            self.client, state.get("requirement", ""), min_score=0.72, top_k=2
        )
        has_critique = any(
            "model" in (p.get("human_critique") or "").lower() or "hardcode" in (p.get("human_critique") or "").lower()
            for p in past_learnings
        )
        if has_critique:
            return json.dumps({
                "impacted_components": ["cart"],
                "design_rationale": "Decouple coupon data model into cart/models.py to satisfy architectural governance, and implement apply_discount in cart/services.py",
                "file_changes": [
                    {"file": "cart/models.py", "action": "modify", "description": "Add Coupon dataclass and VALID_COUPONS dictionary"},
                    {"file": "cart/services.py", "action": "modify", "description": "Implement apply_discount using VALID_COUPONS"}
                ],
                "constraints": ["Do not touch payments/", "Do not hardcode constants in services.py"]
            })
        else:
            return json.dumps({
                "impacted_components": ["cart"],
                "design_rationale": "Add discount coupon logic directly to cart/services.py",
                "file_changes": [
                    {"file": "cart/services.py", "action": "modify", "description": "Add coupon logic to CartService"}
                ],
                "constraints": ["Do not touch payments/"]
            })
