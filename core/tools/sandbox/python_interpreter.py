"""
Python 解释器

Author: Gongmin Wei
Date: 2026-04-07
"""
from .docker_executor import DockerExecutor


def python_interpreter(code: str) -> str:
    """执行 Python 代码，
    适用于计算、逻辑校验、数据处理等场景，
    环境依赖仅包括 numpy、pandas，
    暂不支持生成文件、绘图、联网等操作。
    """
    executor = DockerExecutor()
    return executor.run_python_code(code.strip())