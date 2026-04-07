"""
连接 Agent 和 Docker
支持 [代码段] 和 [本地 Python 文件] 执行

Author: Gongmin Wei
Date: 2026-04-07
"""
import os
import docker
from docker.errors import APIError, NotFound


class DockerExecutor:
    def __init__(self):
        # 连接本地 Docker
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"Docker 连接失败，请检查 Docker Desktop 是否启动: {e}")  # 替换 logger
            raise

        self.image = "python:3.10-slim" # 替换 .env 读取

    def run_python_code(self, code: str, timeout: int = 10):
        """执行代码片段"""
        container = None
        try:
            # 创建并运行容器
            container = self.client.containers.run(
                image=self.image,
                command=["python", "-c", code],
                detach=True,
                network_disabled=True,  # 禁止联网：安全防护
                mem_limit="128m",       # 限制内存：防止内存溢出攻击
                cpu_period=100000,
                cpu_quota=50000         # 限制 CPU：防止死循环耗尽资源
            )

            return self._wait_and_get_logs(container, timeout)
        except Exception as e:
            return f"Error: {str(e)}"
        finally:
            self._cleanup(container)

    def run_python_file(self, script_path: str, timeout: int = 15):
        """执行 Python 文件"""
        if not os.path.exists(script_path):
            return f"Error: 文件 {script_path} 不存在"

        # 将文件所在目录挂载到容器的 /workspace
        abs_path = os.path.abspath(script_path)
        file_dir = os.path.dirname(abs_path)
        file_name = os.path.basename(abs_path)

        container = None
        try:
            container = self.client.containers.run(
                image=self.image,
                command=["python", file_name],
                volumes={file_dir: {'bind': '/workspace', 'mode': 'rw'}},
                working_dir="/workspace",
                detach=True,
                network_disabled=True,
                mem_limit="256m",
            )
            return self._wait_and_get_logs(container, timeout)
        except Exception as e:
            return f"Error: {str(e)}"
        finally:
            self._cleanup(container)

    def _wait_and_get_logs(self, container, timeout):
        """等待容器执行并提取日志"""
        try:
            result = container.wait(timeout=timeout)
            logs = container.logs().decode("utf-8")
            if result.get('StatusCode', 0) != 0:
                return f"Runtime Error:\n{logs}"
            return logs if logs else "Success (No output)"
        except Exception:
            return f"Error: Execution Timeout (Limit: {timeout}s)"

    def _cleanup(self, container):
        """清理容器"""
        if container:
            try:
                container.remove(force=True)
            except (APIError, NotFound):
                pass


if __name__ == "__main__":
    executor = DockerExecutor()

    # 测试常规运行 [代码段]
    # print("--- Test 1: Normal ---")
    # print(executor.run_python_code("print(1 + 1)"))

    # 测试超时逻辑 / 多行代码 [代码段]
    # print("\n--- Test 2: Timeout ---")
    # print(executor.run_python_code("import time; time.sleep(5)", timeout=2))

    # 测试代码报错 [代码段]
    # print("\n--- Test 3: Code Error ---")
    # print(executor.run_python_code("raise ValueError('Oops!')"))

    # 测试常规运行 [代码文件]
    print("--- Test 1: Normal ---")
    print(executor.run_python_file("./test_data/normal.py"))

    # 测试超时逻辑 / 多行代码 [代码文件]
    print("\n--- Test 2: Timeout ---")
    print(executor.run_python_file("./test_data/timeout.py", timeout=2))

    # 测试代码报错 [代码文件]
    print("\n--- Test 3: Code Error ---")
    print(executor.run_python_file("./test_data/codeerr.py"))
