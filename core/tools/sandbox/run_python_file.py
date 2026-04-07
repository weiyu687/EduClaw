"""
Python 解释器， 支持运行本地 Python 文件

Author: Gongmin Wei
Date: 2026-04-07
"""
from .docker_executor import DockerExecutor


def run_python_file(py_file_path: str) -> str:
    """运行 Python 本地文件，
    环境仅依赖 Python 3.10 自带标准库，
    """
    executor = DockerExecutor()

    return executor.run_python_file(py_file_path)