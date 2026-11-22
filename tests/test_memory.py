import os
import sqlite3
import tempfile
from unittest.mock import MagicMock
from orchestrator.memory.store import (
    init_memory_db_sync,
    _cosine_similarity,
    record_workflow_learning_sync,
    retrieve_relevant_learnings_sync,
)


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    v_zero = [0.0, 0.0, 0.0]

    assert _cosine_similarity(v1, v2) == 1.0
    assert _cosine_similarity(v1, v3) == 0.0
    assert _cosine_similarity(v1, v_zero) == 0.0


def test_memory_db_init():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_workflows.db")
        init_memory_db_sync(db_path)
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='institutional_memory'")
            assert cur.fetchone() is not None
        finally:
            conn.close()


def test_record_and_retrieve_learning():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_workflows.db")
        
        # Mock Gemini client for embeddings
        mock_client = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.8, 0.6, 0.0]
        mock_res = MagicMock(embeddings=[mock_embedding])
        mock_client.models.embed_content.return_value = mock_res

        # 1. Record learning
        record_workflow_learning_sync(
            client=mock_client,
            workflow_id="wf-101",
            requirement="Add discount coupon feature",
            design_pattern="Store coupons in cart/models.py",
            code_diff="+ coupon data",
            human_verdict="REJECT",
            human_critique="Never hardcode coupons in services.py; define in models.py",
            db_path=db_path,
        )

        # 2. Retrieve learning with similar query
        mock_query_emb = MagicMock()
        mock_query_emb.values = [0.8, 0.6, 0.0]  # exact match -> score 1.0 >= 0.72
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[mock_query_emb])

        learnings = retrieve_relevant_learnings_sync(
            client=mock_client,
            current_requirement="Add 10% discount coupon to cart",
            min_score=0.72,
            top_k=2,
            db_path=db_path,
        )

        assert len(learnings) == 1
        assert learnings[0]["workflow_id"] == "wf-101"
        assert learnings[0]["human_verdict"] == "REJECT"
        assert "models.py" in learnings[0]["human_critique"]

        # 3. Retrieve with dissimilar query (< 0.72)
        mock_dissimilar = MagicMock()
        mock_dissimilar.values = [0.0, 0.0, 1.0]  # orthogonal -> score 0.0 < 0.72
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[mock_dissimilar])

        unrelated = retrieve_relevant_learnings_sync(
            client=mock_client,
            current_requirement="Completely unrelated notification system",
            min_score=0.72,
            top_k=2,
            db_path=db_path,
        )
        assert len(unrelated) == 0
