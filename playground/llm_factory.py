"""
学习LangChain模型实例化与工具调用

Author: Gongmin Wei
Date: 2026-03-30
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool


load_dotenv()

# 1.获取环境变量
model_name = os.getenv("EDUCLAW_MODEL_NAME")
api_key = os.getenv("DASHSCOPE_API_KEY")
base_url = os.getenv("DASHSCOPE_BASE_URL")

print(f"DEBUG: Model Name is {model_name}")
if not model_name:
    raise ValueError("错误：未能读取到EDUCLAW_MODEL，请检查.env文件变量名是否正确。")

# 2. 初始化LLM对象
llm = ChatOpenAI(
    model=model_name,
    openai_api_key=api_key,
    openai_api_base=base_url
)

# 3. 定义工具
@tool
def get_weather(city: str) -> str:
    """返回指定城市的天气。"""
    return f"最近{city}总是晴天!"

tools = [get_weather]

# 4. 创建 Agent
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt="你是一名智能助手",
)


if __name__ == "__main__":
    result = agent.invoke({
        "messages": [
            ("human", "你好"),
            ("ai", "你好！我是AI助手"),
            ("human", "上海的天气怎么样？")
        ]
    })

    print("\nAI回复:")
    print(result["messages"][-1].content)