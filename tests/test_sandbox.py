import base64
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch
import pytest

from orchestrator.tools.sandbox import Sandbox, SandboxError, ShellResult


def test_pure_posix_path_traversal():
    bad_paths = ["/etc/passwd", "../foo.py", "bar/../../baz.py", "/app/secret"]
    for p in bad_paths:
        path = PurePosixPath(p)
        assert path.is_absolute() or ".." in path.parts


def test_base64_generation():
    content = "print('hello Pine Labs')\n"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == content


def test_sandbox_safe_write_path_traversal_rejection():
    with patch("docker.from_env") as mock_docker:
        mock_container = MagicMock()
        mock_docker.return_value.containers.get.return_value = mock_container
        sb = Sandbox("test-sandbox")

        with pytest.raises(ValueError, match="Path traversal detected"):
            sb.safe_write_file("/workspace", "../evil.py", "malicious")

        with pytest.raises(ValueError, match="Path traversal detected"):
            sb.safe_write_file("/workspace", "/root/bad.py", "malicious")


def test_sandbox_safe_write_file_command():
    with patch("docker.from_env") as mock_docker:
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(output=(b"", b""), exit_code=0)
        mock_docker.return_value.containers.get.return_value = mock_container

        sb = Sandbox("test-sandbox")
        sb.safe_write_file("/workspace", "cart/services.py", "hello")

        # Verify command sent to container
        assert mock_container.exec_run.called
        cmd_arg = mock_container.exec_run.call_args[1]["cmd"]
        assert cmd_arg[0] == "bash"
        assert cmd_arg[1] == "-c"
        assert "base64 -d" in cmd_arg[2]
        assert "cart/services.py" in cmd_arg[2]


def test_sandbox_run_checked_failure():
    with patch("docker.from_env") as mock_docker:
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(output=(b"", b"error details"), exit_code=1)
        mock_docker.return_value.containers.get.return_value = mock_container

        sb = Sandbox("test-sandbox")
        with pytest.raises(SandboxError, match="Command failed"):
            sb.run_checked("false", "/workspace")


def test_sandbox_rollback_violations():
    with patch("docker.from_env") as mock_docker:
        mock_container = MagicMock()
        # Mock tracked files in main: cart/models.py is tracked, secret.py is not
        mock_container.exec_run.side_effect = [
            MagicMock(output=(b"cart/models.py\n", b""), exit_code=0),  # git ls-tree
            MagicMock(output=(b"", b""), exit_code=0),                  # git checkout main -- cart/models.py
            MagicMock(output=(b"", b""), exit_code=0),                  # git rm -f secret.py
        ]
        mock_docker.return_value.containers.get.return_value = mock_container

        sb = Sandbox("test-sandbox")
        sb.rollback_violations("/workspace", "feat/test", ["cart/models.py", "secret.py"])
        assert mock_container.exec_run.call_count == 3
