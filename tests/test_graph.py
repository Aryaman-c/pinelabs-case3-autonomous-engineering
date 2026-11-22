from unittest.mock import MagicMock
from orchestrator.graph import build_graph


def test_graph_compilation():
    mock_sb = MagicMock()
    mock_cp = MagicMock()
    graph = build_graph(mock_sb, mock_cp)
    assert graph is not None

    expected_nodes = {
        "ANALYSIS", "TASK_SELECT", "ARCHITECTURE", "TEST_WRITING",
        "DEVELOPMENT", "QA_CHECK", "LINT_CHECK", "SECURITY_CHECK",
        "RELEASE_PREP", "CONFLICT_PAUSE", "SECURITY_HOLD", "HUMAN_REVIEW", "MERGE_TAG"
    }
    assert expected_nodes.issubset(set(graph.nodes.keys()))
