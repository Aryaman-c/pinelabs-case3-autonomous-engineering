import json
import os
from orchestrator.agents.base import BaseAgent
from orchestrator.state import WorkflowState
from orchestrator.tools.sandbox import Sandbox


class AnalystAgent(BaseAgent):
    model = os.environ.get("GEMINI_MODEL_FAST", "gemini-2.0-flash-exp")
    node_name = "ANALYSIS"

    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox

    def _get_repo_summary(self, workdir: str) -> str:
        res = self.sandbox.run("find . -maxdepth 3 -name '*.py' | sort | head -30", workdir)
        return res.stdout if res.success else ""

    def build_prompt(self, state: WorkflowState) -> str:
        repo_files = self._get_repo_summary(state["repo_path"])
        return f"""You are a Lead Systems Analyst.
Analyze the following product requirement for our Payments/Cart microservice:

REQUIREMENT:
{state['requirement']}

REPOSITORY CONTEXT:
{repo_files}

Decompose into 3-6 clear, independently testable acceptance criteria and 1-3 atomic tasks.
Assign priority 1 to the foundational task.

Return ONLY JSON:
{{
  "acceptance_criteria": [
    "string"
  ],
  "tasks": [
    {{
      "id": "TASK-001",
      "title": "string",
      "description": "string",
      "priority": 1
    }}
  ]
}}
"""

    def parse_output(self, raw: str) -> dict:
        data = json.loads(raw)
        assert isinstance(data.get("acceptance_criteria"), list) and len(data["acceptance_criteria"]) >= 2
        assert isinstance(data.get("tasks"), list) and len(data["tasks"]) >= 1
        for t in data["tasks"]:
            assert all(k in t for k in ("id", "title", "description", "priority"))
        return data

    def state_update(self, parsed: dict, state: WorkflowState) -> dict:
        return {
            "acceptance_criteria": parsed["acceptance_criteria"],
            "tasks": parsed["tasks"],
        }

    def get_demo_fallback(self, state: WorkflowState) -> str:
        return json.dumps({
            "acceptance_criteria": [
                "Apply 10% discount when coupon 'SAVE10' is applied to cart total",
                "Apply 20% discount when coupon 'SAVE20' is applied to cart total",
                "Raise ValueError with message 'Invalid coupon code' for invalid or unrecognized coupons",
                "Preserve all existing cart baseline methods and pass all unit tests"
            ],
            "tasks": [
                {
                    "id": "TASK-001",
                    "title": "Add discount coupon support to cart",
                    "description": "Implement coupon validation and discount calculation in cart microservice",
                    "priority": 1
                }
            ]
        })
