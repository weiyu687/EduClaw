"""
Python 解释器， 支持运行代码片段

Author: Gongmin Wei
Date: 2026-04-07
"""
from .docker_executor import DockerExecutor


def run_python_code(code: str) -> str:
    """执行 Python 代码，
    适用于计算、逻辑校验、数据处理等场景，
    环境仅依赖 Python 3.10 自带标准库，
    暂不支持生成文件、绘图、联网等操作。
    """
    executor = DockerExecutor()

    return executor.run_python_code(code.strip())