from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """返回指定城市的天气。"""
    # 这里可以接入真正的天气 API
    return f"EduClaw 实时监测：最近 {city} 总是晴天，适合学习！"

# 导出工具列表供 MCP Server 使用
edu_tools = [get_weather]