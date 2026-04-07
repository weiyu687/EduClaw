"""
连接 Agent 和 Docker

Author: Gongmin Wei
Date: 2026-04-06
"""
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

            # 等待容器执行完毕或超时
            try:
                result = container.wait(timeout=timeout)
                # 检查退出码
                result.get('StatusCode', 0)
            except Exception:
                return f"Error: Execution Timeout (Limit: {timeout}s)"

            # 获取输出日志
            logs = container.logs(tail=100).decode("utf-8")

            return logs

        except Exception as e:
            return f"Error: {str(e)}"

        finally:
            if container:
                try:
                    container.remove(force=True)
                except (APIError, NotFound):
                    pass


if __name__ == "__main__":
    executor = DockerExecutor()

    # 测试常规运行
    print("--- Test 1: Normal ---")
    print(executor.run_python_code("print(1 + 1)"))

    # 测试超时逻辑 / 多行代码
    print("\n--- Test 2: Timeout ---")
    print(executor.run_python_code("import time; time.sleep(5)", timeout=2))

    # 测试代码报错
    print("\n--- Test 3: Code Error ---")
    print(executor.run_python_code("raise ValueError('Oops!')"))