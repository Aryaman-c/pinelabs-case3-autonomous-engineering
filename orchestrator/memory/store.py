import json
import math
import sqlite3
import os
from google import genai
import structlog

log = structlog.get_logger()
DB_PATH = os.environ.get("WORKFLOW_DB_PATH", "/app/data/workflows.db")

CREATE_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS institutional_memory (
    memory_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    requirement TEXT NOT NULL,
    embedding TEXT NOT NULL,
    design_pattern TEXT,
    code_diff TEXT,
    human_verdict TEXT NOT NULL,
    human_critique TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def _get_db_path(db_path: str = None) -> str:
    path = db_path or os.environ.get("WORKFLOW_DB_PATH", "data/workflows.db")
    if path.startswith("/app/") and not os.path.exists("/app"):
        path = path.replace("/app/", "")
    return path


def init_memory_db_sync(db_path: str = None):
    target = _get_db_path(db_path)
    dirname = os.path.dirname(target)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(target)
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute(CREATE_MEMORY_TABLE)
        conn.commit()
    finally:
        conn.close()


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


def _pseudo_embedding(text: str, dim: int = 768) -> list[float]:
    import hashlib
    vec = [0.0] * dim
    words = text.lower().replace("'", "").replace('"', "").replace(".", " ").replace(",", " ").split()
    for w in words:
        if not w:
            continue
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


def _get_embedding(client: genai.Client, text: str) -> list[float]:
    emb_model = os.environ.get("GEMINI_MODEL_EMBEDDING", "gemini-embedding-001")
    last_err = None
    for m in (emb_model, "text-embedding-004"):
        try:
            res = client.models.embed_content(model=m, contents=text)
            return res.embeddings[0].values
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Embedding failed: {last_err}")


def record_workflow_learning_sync(
    client: genai.Client,
    workflow_id: str,
    requirement: str,
    design_pattern: str,
    code_diff: str,
    human_verdict: str,
    human_critique: str = "",
    db_path: str = None,
):
    target_db = _get_db_path(db_path)
    embedding = _get_embedding(client, requirement)

    init_memory_db_sync(target_db)
    conn = sqlite3.connect(target_db)
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute(
            """INSERT OR REPLACE INTO institutional_memory 
               (memory_id, workflow_id, requirement, embedding, design_pattern, code_diff, human_verdict, human_critique)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_id, workflow_id, requirement, json.dumps(embedding),
                design_pattern, code_diff[:4000], human_verdict, human_critique
            )
        )
        conn.commit()
    finally:
        conn.close()
    log.info("memory.recorded", workflow_id=workflow_id, verdict=human_verdict)


def retrieve_relevant_learnings_sync(
    client: genai.Client,
    current_requirement: str,
    min_score: float = 0.72,
    top_k: int = 2,
    db_path: str = None,
) -> list[dict]:
    target_db = _get_db_path(db_path)
    target_emb = _get_embedding(client, current_requirement)

    if not os.path.exists(target_db):
        return []

    candidates = []
    conn = sqlite3.connect(target_db)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM institutional_memory")
        rows = cursor.fetchall()
        for row in rows:
            stored_emb = json.loads(row["embedding"])
            score = _cosine_similarity(target_emb, stored_emb)
            if score >= min_score:
                candidates.append((score, dict(row)))
    finally:
        conn.close()

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in candidates[:top_k]]
