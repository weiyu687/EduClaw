"""
连接 Agent 和 Docker (优化版)

Author: Gongmin Wei
Date: 2026-04-06
"""
import docker
from docker.errors import APIError, NotFound


class DockerExecutor:
    def __init__(self):
        # 自动连接本地 Docker
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"Docker 连接失败，请检查 Docker Desktop 是否启动: {e}")
            raise

        self.image = "python:3.10-slim"

    def run_python_code(self, code: str, timeout: int = 10):
        container = None
        try:
            # 1. 创建并运行容器
            container = self.client.containers.run(
                image=self.image,
                command=["python", "-c", code],
                detach=True,
                network_disabled=True,  # 禁止联网：安全防护
                mem_limit="128m",       # 限制内存：防止内存溢出攻击
                cpu_period=100000,
                cpu_quota=50000         # 限制 CPU：防止死循环耗尽资源
            )

            # 2. 等待容器执行完毕或超时
            try:
                # wait() 是 Docker SDK 提供的标准等待方法
                # 它比手动写 while 循环更高效、更准确
                result = container.wait(timeout=timeout)
                # 检查退出码（非0通常代表代码报错）
                exit_code = result.get('StatusCode', 0)
            except Exception:
                # 如果触发异常，说明执行超时
                return f"Error: Execution Timeout (Limit: {timeout}s)"

            # 3. 获取输出日志
            # tail=100 防止日志过大撑爆内存
            logs = container.logs(tail=100).decode("utf-8")

            # 如果代码报错（exit_code != 0），我们同时返回日志，方便 Agent 调试
            return logs

        except Exception as e:
            return f"Error: {str(e)}"

        finally:
            # 4. 核心修复：无论成功、失败或超时，直接使用 force=True 彻底清理
            if container:
                try:
                    # force=True 会同时处理正在运行和已停止的容器
                    # 这样就彻底避免了 "cannot kill container" 的 409 报错
                    container.remove(force=True)
                except (APIError, NotFound):
                    pass


if __name__ == "__main__":
    executor = DockerExecutor()

    # 测试常规运行
    print("--- Test 1: Normal ---")
    print(executor.run_python_code("print(1 + 1)"))

    # 测试超时逻辑
    print("\n--- Test 2: Timeout ---")
    print(executor.run_python_code("import time; time.sleep(5)", timeout=2))

    # 测试代码报错
    print("\n--- Test 3: Code Error ---")
    print(executor.run_python_code("raise ValueError('Oops!')"))