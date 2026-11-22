import json
import os
from orchestrator.agents.base import BaseAgent
from orchestrator.state import WorkflowState, CodeChange
from orchestrator.tools.sandbox import Sandbox
from orchestrator.memory.store import retrieve_relevant_learnings_sync


class DeveloperAgent(BaseAgent):
    model = os.environ.get("GEMINI_MODEL_SMART", "gemini-2.0-pro-exp")
    node_name = "DEVELOPMENT"

    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox

    def _read_files_to_modify(self, workdir: str, allowed_files: list[str]) -> str:
        parts = []
        for rel_path in allowed_files:
            res = self.sandbox.run(f"cat {rel_path} 2>/dev/null", workdir)
            content = res.stdout if res.success and res.stdout.strip() else "(file does not exist yet)"
            parts.append(f"=== File: {rel_path} ===\n{content}")
        return "\n\n".join(parts)[:10000]

    def build_prompt(self, state: WorkflowState) -> str:
        task = state["selected_task"]
        design = state["design_proposal"]
        test_report = state.get("test_report")
        security_report = state.get("security_report")
        retry_count = state.get("retry_counts", {}).get("developer", 0)
        workdir = state["repo_path"]

        allowed_files = [fc["file"] for fc in design.get("file_changes", [])]
        existing_code = self._read_files_to_modify(workdir, allowed_files)

        feedback = []
        if test_report and not test_report.get("success") and retry_count > 0:
            err_str = "\n".join(test_report.get("errors", []))
            feedback.append(f"PREVIOUS TEST FAILURES:\n{err_str}\nFix the implementation to satisfy all tests.")

        if security_report and security_report.get("critical_block"):
            findings = json.dumps(security_report.get("bandit_findings", []), indent=2)
            feedback.append(f"CRITICAL SECURITY FINDINGS FROM BANDIT:\n{findings}\nRemediate immediately.")

        # RAG self-evolution context
        req_text = state.get("requirement", "")
        past_learnings = retrieve_relevant_learnings_sync(
            self.client, req_text, min_score=0.72, top_k=2
        ) if req_text else []
        if past_learnings:
            past_critiques = "\n".join(f"- {p['human_critique']}" for p in past_learnings if p.get('human_critique'))
            if past_critiques:
                feedback.append(f"INSTITUTIONAL CRITIQUES FROM SIMILAR TASKS:\n{past_critiques}")

        feedback_str = "\n\n".join(feedback)

        return f"""You are a Senior Software Engineer implementing this feature.
TASK:
{task['id']}: {task['title']}
{task['description']}

DESIGN CONTRACT:
{design['design_rationale']}
Allowed Files: {json.dumps(allowed_files)}

CURRENT SOURCE CODE (Preserve existing functions; DO NOT delete baseline methods):
{existing_code}

{feedback_str}

Return JSON with complete file contents for each allowed file:
{{
  "files": [
    {{"path": "cart/services.py", "content": "..."}},
    {{"path": "cart/models.py", "content": "..."}}
  ],
  "implementation_notes": "..."
}}
"""

    def parse_output(self, raw: str) -> dict:
        data = json.loads(raw)
        assert isinstance(data.get("files"), list) and len(data["files"]) > 0
        return data

    def state_update(self, parsed: dict, state: WorkflowState) -> dict:
        workdir = state["repo_path"]
        branch_name = f"feat/{state['workflow_id'][:8]}-{state['selected_task']['id'].lower()}"
        design = state["design_proposal"]
        allowed = {fc["file"] for fc in design.get("file_changes", [])}
        retry_count = state.get("retry_counts", {}).get("developer", 0)

        self.sandbox.run_checked(f"git checkout {branch_name}", workdir)

        for f in parsed["files"]:
            self.sandbox.safe_write_file(workdir, f["path"], f["content"])

        self.sandbox.run("git add -A", workdir)
        self.sandbox.run(f"git commit -m 'feat: implement {state['selected_task']['id']}'", workdir)

        changed = self.sandbox.git_diff_files(workdir, branch_name)
        # Exclude test files from violation checks if modified by test engineer
        violations = [f for f in changed if f not in allowed and not f.startswith("tests/")]
        conflict_detected = len(violations) > 0

        if conflict_detected:
            self.sandbox.rollback_violations(workdir, branch_name, violations)
            self.sandbox.run("git add -A && git commit -m 'fix: rollback unauthorized modifications'", workdir)

        diff = self.sandbox.run_checked(f"git diff main...{branch_name}", workdir).stdout
        actual_changed = self.sandbox.git_diff_files(workdir, branch_name)

        code_change: CodeChange = {
            "branch_name": branch_name,
            "files_modified": actual_changed,
            "diff": diff,
            "implementation_notes": parsed.get("implementation_notes", ""),
            "conflict_detected": conflict_detected,
            "conflict_detail": f"Violations outside design allowlist: {violations}" if conflict_detected else "",
        }

        retries = dict(state.get("retry_counts", {}))
        retries["developer"] = retry_count + 1

        return {
            "code_change": code_change,
            "retry_counts": retries,
            "human_decision": None,
        }

    def get_demo_fallback(self, state: WorkflowState) -> str:
        design = state.get("design_proposal") or {}
        allowed_files = [fc["file"] for fc in design.get("file_changes", [])]

        if "cart/models.py" in allowed_files:
            models_code = """from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Coupon:
    code: str
    discount_rate: float


VALID_COUPONS = {
    "SAVE10": Coupon("SAVE10", 0.10),
    "SAVE20": Coupon("SAVE20", 0.20),
}


@dataclass
class CartItem:
    product_id: str
    name: str
    price: float
    quantity: int = 1

    @property
    def subtotal(self) -> float:
        return self.price * self.quantity


@dataclass
class Cart:
    cart_id: str
    items: list[CartItem] = field(default_factory=list)
"""
            services_code = """from typing import Optional
from cart.models import Cart, CartItem, VALID_COUPONS


class CartService:
    def __init__(self):
        self._carts: dict[str, Cart] = {}

    def create_cart(self, cart_id: str) -> Cart:
        cart = Cart(cart_id=cart_id)
        self._carts[cart_id] = cart
        return cart

    def get_cart(self, cart_id: str) -> Optional[Cart]:
        return self._carts.get(cart_id)

    def add_item(self, cart_id: str, item: CartItem) -> Cart:
        cart = self._carts[cart_id]
        cart.items.append(item)
        return cart

    def get_total(self, cart_id: str) -> float:
        cart = self._carts[cart_id]
        return sum(item.subtotal for item in cart.items)

    def apply_discount(self, cart_id: str, coupon: str) -> float:
        if coupon not in VALID_COUPONS:
            raise ValueError(f"Invalid coupon code: {coupon}")
        coupon_obj = VALID_COUPONS[coupon]
        total = self.get_total(cart_id)
        return total * (1.0 - coupon_obj.discount_rate)
"""
            return json.dumps({
                "files": [
                    {"path": "cart/models.py", "content": models_code},
                    {"path": "cart/services.py", "content": services_code}
                ],
                "implementation_notes": "Defined coupons in cart/models.py per architectural governance."
            })
        else:
            services_code = """from typing import Optional
from cart.models import Cart, CartItem

COUPONS = {"SAVE10": 0.10, "SAVE20": 0.20}


class CartService:
    def __init__(self):
        self._carts: dict[str, Cart] = {}

    def create_cart(self, cart_id: str) -> Cart:
        cart = Cart(cart_id=cart_id)
        self._carts[cart_id] = cart
        return cart

    def get_cart(self, cart_id: str) -> Optional[Cart]:
        return self._carts.get(cart_id)

    def add_item(self, cart_id: str, item: CartItem) -> Cart:
        cart = self._carts[cart_id]
        cart.items.append(item)
        return cart

    def get_total(self, cart_id: str) -> float:
        cart = self._carts[cart_id]
        return sum(item.subtotal for item in cart.items)

    def apply_discount(self, cart_id: str, coupon: str) -> float:
        if coupon not in COUPONS:
            raise ValueError(f"Invalid coupon code: {coupon}")
        total = self.get_total(cart_id)
        return total * (1.0 - COUPONS[coupon])
"""
            return json.dumps({
                "files": [
                    {"path": "cart/services.py", "content": services_code}
                ],
                "implementation_notes": "Implemented coupon discounts directly inside CartService."
            })
