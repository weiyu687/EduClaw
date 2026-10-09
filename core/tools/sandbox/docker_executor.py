"""Docker-based Python execution with explicit error semantics."""
import os
import logging
import requests
import docker
from docker.errors import APIError, NotFound
from urllib3.exceptions import ReadTimeoutError

logger = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """An execution failure that should become an MCP isError result."""
    def __init__(self, message, *, category="execution_error", uncertain=False):
        super().__init__(message)
        self.category = category
        self.uncertain = uncertain


class ToolExecutionTimeout(ToolExecutionError):
    def __init__(self, message, *, uncertain=True, timeout_seconds=None):
        super().__init__(message, category="timeout", uncertain=uncertain)
        self.timeout_seconds = timeout_seconds


class DockerExecutor:
    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as exc:
            raise ToolExecutionError(f"Docker connection failed: {exc}", category="infrastructure_error") from exc
        self.image = "python:3.10-slim"

    def run_python_code(self, code: str, timeout: int = 10):
        container = None
        try:
            container = self.client.containers.run(
                image=self.image,
                command=["python", "-c", code],
                detach=True,
                network_disabled=True,
                mem_limit="128m",
                cpu_period=100000,
                cpu_quota=50000,
            )
            return self._wait_and_get_logs(container, timeout)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Docker execution failed: {exc}", category="infrastructure_error") from exc
        finally:
            self._cleanup(container)

    def run_python_file(self, script_path: str, timeout: int = 15):
        if not os.path.isfile(script_path):
            raise ToolExecutionError(f"Python file not found: {script_path}", category="input_error")
        abs_path = os.path.abspath(script_path)
        file_dir = os.path.dirname(abs_path)
        file_name = os.path.basename(abs_path)
        container = None
        try:
            container = self.client.containers.run(
                image=self.image,
                command=["python", file_name],
                volumes={file_dir: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                detach=True,
                network_disabled=True,
                mem_limit="256m",
            )
            return self._wait_and_get_logs(container, timeout)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Docker execution failed: {exc}", category="infrastructure_error") from exc
        finally:
            self._cleanup(container)

    def _wait_and_get_logs(self, container, timeout):
        try:
            result = container.wait(timeout=timeout)
        except (requests.exceptions.Timeout, ReadTimeoutError, TimeoutError) as exc:
            raise ToolExecutionTimeout(f"Docker API wait timed out (limit: {timeout}s); process termination pending confirmation", timeout_seconds=timeout) from exc
        except Exception as exc:
            # Docker SDK may wrap urllib3 ReadTimeoutError in another exception.
            chain = exc
            while chain is not None:
                if isinstance(chain, (requests.exceptions.Timeout, ReadTimeoutError, TimeoutError)):
                    raise ToolExecutionTimeout(
                        f"Docker API wait timed out (limit: {timeout}s); process termination pending confirmation", timeout_seconds=timeout
                    ) from exc
                chain = chain.__cause__ or chain.__context__
            raise ToolExecutionError(f"Docker wait failed: {exc}", category="infrastructure_error") from exc
        try:
            logs = container.logs().decode("utf-8", errors="replace")
        except Exception as exc:
            raise ToolExecutionError(f"Docker logs failed: {exc}", category="infrastructure_error") from exc
        exit_code = result.get("StatusCode")
        if exit_code is None:
            raise ToolExecutionError("Docker did not return an exit status", category="infrastructure_error")
        if exit_code != 0:
            raise ToolExecutionError(f"Runtime Error (exit code {exit_code}):\n{logs}", category="runtime_error")
        return logs if logs else "Success (No output)"

    def _cleanup(self, container):
        if container is not None:
            try:
                container.remove(force=True)
            except (APIError, NotFound, Exception) as exc:
                logger.warning("Failed to clean up Docker container: %s", exc)
