# Autonomous Enterprise Engineering Organisation — 2-Run Demo Protocol

## Overview
This protocol demonstrates the end-to-end autonomous engineering lifecycle, bounded human governance, and institutional self-evolution via zero-infrastructure RAG memory.

---

## Run 1: First Attempt (Flawed Architecture & Human Rejection)

### 1. Submit Requirement
- Open `http://localhost:8000`
- Submit requirement in the mission control console:
  > *"Add discount coupon feature to cart. Support 'SAVE10' (10% discount). Reject invalid codes."*

### 2. Observe Autonomous Graph Execution
The orchestrator executes the standard operating procedure (SOP):
- **ANALYSIS**: Analyst decomposes requirement into acceptance criteria and priority-1 tasks.
- **TASK_SELECT**: Task selector assigns foundational coupon implementation.
- **ARCHITECTURE**: Architect defines minimal blast radius proposal.
- **TEST_WRITING**: Test Engineer writes pytest assertions in `tests/test_cart.py` (TDD).
- **DEVELOPMENT**: Developer writes code to satisfy the tests.
- **QUALITY GATES (Parallel Fan-Out)**:
  - `pytest --json-report` validates functional correctness.
  - `ruff` validates formatting and style in 15ms.
  - `bandit` + `pip-audit` checks diff AST for vulnerabilities and CVEs.
- **RELEASE_PREP**: Release agent compiles the evidence package.

### 3. Human Review Checkpoint (`HUMAN_REVIEW`)
The workflow pauses automatically via LangGraph's `interrupt_before`.
1. Inspect the code diff: notice that the developer placed a hardcoded discount dictionary directly in `cart/services.py`.
2. In the Human Review Feedback box, type:
   > *"Architectural Violation: Never hardcode discount mappings inside services.py. Define coupons in cart/models.py."*
3. Click **Reject**.

### 4. Memory Persistence Verification
The rejection verdict and critique are embedded using `text-embedding-004` and stored in SQLite:
```sql
SELECT workflow_id, human_verdict, human_critique FROM institutional_memory;
```

---

## Run 2: Second Attempt (Autonomous Self-Evolution via RAG)

### 1. Submit Similar Requirement
- Submit a follow-up or similar coupon requirement:
  > *"Add discount coupon feature to cart. Support 'SAVE10' (10% discount) and 'SAVE20' (20% discount)."*

### 2. Self-Evolving Execution
- **RAG Retrieval**: The RAG engine computes cosine similarity against past memory (> 0.85).
- **Architect Adaptation**: The Architect Agent receives Run 1's human critique in its prompt and declares `file_changes` for *both* `cart/models.py` and `cart/services.py`.
- **Developer Implementation**: The Developer places coupon models and constants in `cart/models.py` and imports them into `cart/services.py`.
- **Deterministic Quality Gates**: Pytest passes, Ruff passes (0 errors), Bandit reports 0 HIGH vulnerabilities.

### 3. Human Approval & Merge
1. The workflow reaches `HUMAN_REVIEW` with an APPROVED recommendation from Release Agent.
2. Reviewer clicks **Approve & Merge**.
3. UI displays the validated non-fast-forward merge command:
   ```bash
   git checkout main && git merge --no-ff feat/<branch> && git push origin main
   ```

---

## Full Verification Checklist
```bash
[x] docker compose build & up configurations hardened (Stage 1)
[x] WorkflowState and append-only reducers validated (Stage 2)
[x] Sandbox bridge, safe Base64 writes & git rollback engine validated (Stage 3)
[x] Synchronous SQLite RAG memory & text-embedding-004 store validated (Stage 4)
[x] BaseAgent LLM resilience & fail-fast retry loop validated (Stage 5)
[x] Analyst Agent acceptance criteria decomposition validated (Stage 6)
[x] Architect Agent blast radius contract validated (Stage 7)
[x] TDD Test Engineer Agent test authoring validated (Stage 8)
[x] Developer Agent self-correction & context preservation validated (Stage 9)
[x] QA, Lint, and Security deterministic parallel quality gates validated (Stage 10)
[x] Release synthesis agent evidence packaging validated (Stage 11)
[x] LangGraph state machine & human interrupt gates validated (Stage 12)
[x] FastAPI web server, async SSE stream & interactive dashboard validated (Stage 13)
[x] Sample microservice baseline models, services & unit tests validated (Stage 14)
[x] End-to-end 2-run self-evolution demo protocol documented (Stage 15)
```
