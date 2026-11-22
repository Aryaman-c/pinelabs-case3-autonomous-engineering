import base64
import os
from pathlib import PurePosixPath
import shlex
import subprocess
from dataclasses import dataclass
import docker
from docker.errors import DockerException
import structlog

log = structlog.get_logger()


@dataclass
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int
    success: bool


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, container_name: str, timeout: int = 5):
        self.container_name = container_name
        self.timeout = timeout
        try:
            self.client = docker.from_env(timeout=timeout)
            _ = self.container
        except DockerException as e:
            raise SandboxError(f"Sandbox container error: {e}")

    @property
    def container(self):
        try:
            c = self.client.containers.get(self.container_name)
            if c.status != "running":
                c.start()
            return c
        except Exception:
            try:
                subprocess.run(["docker", "compose", "up", "-d", "sandbox"], check=False, capture_output=True)
                return self.client.containers.get(self.container_name)
            except Exception as e:
                raise SandboxError(f"Sandbox container '{self.container_name}' error: {e}")

    def run(self, command: str, workdir: str) -> ShellResult:
        log.info("sandbox.exec", cmd=command, cwd=workdir)
        for attempt in range(2):
            try:
                res = self.container.exec_run(
                    cmd=["bash", "-c", command],
                    workdir=workdir,
                    user="agent",
                    demux=True,
                )
                stdout = res.output[0].decode("utf-8", errors="replace") if res.output[0] else ""
                stderr = res.output[1].decode("utf-8", errors="replace") if res.output[1] else ""
                if res.exit_code == 128 and ("procReady not received" in stdout or "procReady not received" in stderr or "OCI runtime" in stdout or "OCI runtime" in stderr):
                    if attempt == 0:
                        log.warning("sandbox.exec_proc_ready_retry", msg="Container exec wedged; restarting container and retrying...")
                        try:
                            self.container.restart()
                        except Exception:
                            pass
                        continue
                return ShellResult(stdout=stdout, stderr=stderr, exit_code=res.exit_code, success=res.exit_code == 0)
            except Exception as e:
                if attempt == 0:
                    try:
                        self.container.restart()
                        continue
                    except Exception:
                        pass
                raise SandboxError(f"Container exec failure: {e}")

    def run_checked(self, command: str, workdir: str) -> ShellResult:
        res = self.run(command, workdir)
        if not res.success:
            raise SandboxError(f"Command failed ({res.exit_code}): {res.stderr}\nStdout: {res.stdout}")
        return res

    def init_workflow_repo(self, workflow_id: str, sample_repo_path: str) -> str:
        workdir = f"/workspace/runs/{workflow_id}"
        self.container.exec_run(cmd=["bash", "-c", f"mkdir -p {workdir}"], user="agent")

        import io
        import tarfile
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(sample_repo_path, arcname=".")
        tar_bytes = tar_stream.getvalue()

        p = subprocess.Popen(
            ["docker", "exec", "-i", self.container_name, "tar", "--no-same-owner", "-xf", "-", "-C", workdir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, err = p.communicate(input=tar_bytes)
        if p.returncode != 0:
            raise SandboxError(f"Failed to copy repository into sandbox: {err.decode('utf-8', errors='replace')}")

        self.run_checked("git init", workdir)
        self.run_checked("git config user.name 'Enterprise Agent'", workdir)
        self.run_checked("git config user.email 'agent@enterprise.local'", workdir)
        self.run_checked("git add -A", workdir)
        self.run_checked("git commit -m 'initial baseline'", workdir)
        self.run_checked("git branch -M main", workdir)
        return workdir

    def safe_write_file(self, workdir: str, rel_path: str, content: str) -> None:
        pure_path = PurePosixPath(rel_path)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise ValueError(f"Path traversal detected: {rel_path}")

        quoted_path = shlex.quote(str(pure_path))
        b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        cmd = f"mkdir -p $(dirname {quoted_path}) && echo '{b64_content}' | base64 -d > {quoted_path}"
        self.run_checked(cmd, workdir)

    def git_diff_files(self, workdir: str, branch: str, base: str = "main") -> list[str]:
        cmd = f"git diff --name-only --diff-filter=ACMR {base}...{branch}"
        res = self.run_checked(cmd, workdir)
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]

    def rollback_violations(self, workdir: str, branch: str, violations: list[str]) -> None:
        tracked_res = self.run("git ls-tree -r main --name-only", workdir)
        tracked_main = set(tracked_res.stdout.splitlines()) if tracked_res.success else set()

        for f in violations:
            quoted = shlex.quote(f)
            if f in tracked_main:
                self.run(f"git checkout main -- {quoted}", workdir)
            else:
                self.run(f"git rm -f {quoted} || rm -f {quoted}", workdir)
            log.warning("sandbox.rolled_back", file=f)
