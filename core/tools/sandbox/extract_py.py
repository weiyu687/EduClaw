"""Read Python source from a local file."""
from .docker_executor import ToolExecutionError


def extract_py(py_path: str) -> str:
    try:
        with open(py_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as exc:
        raise ToolExecutionError(
            f"Failed to extract Python code from {py_path}: {exc}", category="input_error"
        ) from exc
