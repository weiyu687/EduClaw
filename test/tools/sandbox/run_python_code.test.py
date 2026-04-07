"""
测试 tool: run_python_code Python 解释器工具

Author: Gongmin Wei
Date: 2026-04-07
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool

from docker_executor import DockerExecutor


executor = DockerExecutor()

@tool
def python_interpreter(code: str) -> str:
    """Python 解释器"""
    print(f"\n>>> [系统监控] Agent 正在请求 Docker 执行代码:\n{code}\n")
    return executor.run_python_code(code.strip())

def main():
    load_dotenv()

    model_name = os.getenv("EDUCLAW_MODEL_NAME")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")

    if not model_name:
        raise ValueError("Error: Failed to load model configuration, please check the .env file.")

    llm = ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url
    )

    tools = [python_interpreter]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="你是一名强大的编程助手。如果问题涉及计算或数据处理，请编写代码并调用 python_interpreter 执行。"
    )

    print("\n--- 正在调用 Agent 执行计算任务 ---")

    # 模拟对话输入
    query = "请计算第 10 个斐波那契数是多少？并验证它是否为质数。"

    result = agent.invoke({
        "messages": [
            ("human", query)
        ]
    })

    print("\nAI回复:")
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()