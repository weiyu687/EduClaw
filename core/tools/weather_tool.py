"""
试验

Author: Gongmin Wei
Date: 2026-04-02
"""
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """返回指定城市的天气。"""
    return f"EduClaw 实时监测：最近 {city} 总是晴天，适合学习！"
