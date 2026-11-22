import json
import os
from orchestrator.agents.base import BaseAgent
from orchestrator.state import WorkflowState
from orchestrator.tools.sandbox import Sandbox


class TestEngineerAgent(BaseAgent):
    __test__ = False
    model = os.environ.get("GEMINI_MODEL_FAST", "gemini-2.0-flash-exp")
    node_name = "TEST_WRITING"

    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox

    def build_prompt(self, state: WorkflowState) -> str:
        task = state["selected_task"]
        design = state["design_proposal"]
        criteria = "\n".join(f"- {c}" for c in (state["acceptance_criteria"] or []))
        workdir = state["repo_path"]

        test_file = "tests/test_cart.py"
        res = self.sandbox.run(f"cat {test_file} 2>/dev/null", workdir)
        existing_tests = res.stdout if res.success and res.stdout.strip() else ""

        return f"""You are a Lead QA Engineer writing pytest unit tests in Test-Driven Development (TDD).

TASK:
ID: {task['id']} - {task['title']}
Description: {task['description']}

ACCEPTANCE CRITERIA:
{criteria}

DESIGN RATIONALE:
{design['design_rationale']}

EXISTING TESTS (Must preserve existing baseline tests):
{existing_tests}

Write comprehensive unit tests in pytest that test the new feature thoroughly.
Return ONLY JSON:
{{
  "test_file_path": "tests/test_cart.py",
  "test_file_content": "COMPLETE file content"
}}
"""

    def parse_output(self, raw: str) -> dict:
        data = json.loads(raw)
        assert "test_file_path" in data and "test_file_content" in data
        return data

    def state_update(self, parsed: dict, state: WorkflowState) -> dict:
        workdir = state["repo_path"]
        branch_name = f"feat/{state['workflow_id'][:8]}-{state['selected_task']['id'].lower()}"

        self.sandbox.run_checked("git checkout main", workdir)
        self.sandbox.run(f"git branch -D {branch_name}", workdir)
        self.sandbox.run_checked(f"git checkout -b {branch_name}", workdir)

        self.sandbox.safe_write_file(workdir, parsed["test_file_path"], parsed["test_file_content"])
        self.sandbox.run("git add -A", workdir)
        self.sandbox.run(f"git commit -m 'test: add TDD unit tests for {state['selected_task']['id']}'", workdir)

        return {
            "current_node": self.node_name,
            "agent_history": [{"node": self.node_name, "test_file": parsed["test_file_path"]}],
        }

    def get_demo_fallback(self, state: WorkflowState) -> str:
        content = """import pytest
from cart.models import CartItem
from cart.services import CartService


@pytest.fixture
def service():
    return CartService()


def test_create_cart(service):
    cart = service.create_cart("test-cart")
    assert cart.cart_id == "test-cart"
    assert cart.items == []


def test_add_item_and_total(service):
    service.create_cart("c1")
    service.add_item("c1", CartItem("p1", "Item 1", 10.0, 2))
    assert service.get_total("c1") == 20.0


def test_apply_discount_coupon_save10(service):
    service.create_cart("c1")
    service.add_item("c1", CartItem("p1", "Item 1", 100.0, 1))
    assert service.apply_discount("c1", "SAVE10") == 90.0


def test_apply_discount_coupon_save20(service):
    service.create_cart("c1")
    service.add_item("c1", CartItem("p1", "Item 1", 100.0, 1))
    assert service.apply_discount("c1", "SAVE20") == 80.0


def test_apply_invalid_coupon_raises_error(service):
    service.create_cart("c1")
    service.add_item("c1", CartItem("p1", "Item 1", 100.0, 1))
    with pytest.raises(ValueError):
        service.apply_discount("c1", "INVALID_CODE")
"""
        return json.dumps({
            "test_file_path": "tests/test_cart.py",
            "test_file_content": content
        })
