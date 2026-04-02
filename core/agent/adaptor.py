"""
MCP Tool -> LangChain BaseTool

Author: Gongmin Wei
Date: 2026-04-02
"""
from langchain_core.tools import BaseTool, Tool
from pydantic import BaseModel, create_model
from mcp import types

from core.mcp import MCPClient


def validate_mcp_tool(mcp_tool: types.Tool) -> bool:
    """强校验 MCP 工具"""
    if not mcp_tool.name or not isinstance(mcp_tool.name, str):
        raise ValueError(f"Invalid tool name: {mcp_tool.name}")

    if not mcp_tool.description or len(mcp_tool.description) < 5:
        raise ValueError(f"Tool description is missing or too short: {mcp_tool.name}")

    schema = mcp_tool.inputSchema
    if not isinstance(schema, dict):
        raise ValueError(f"inputSchema must be a dictionary: {mcp_tool.name}")

    if schema.get("type") != "object":
        raise ValueError(f"inputSchema.type must be 'object': {mcp_tool.name}")

    if "properties" not in schema or not isinstance(schema["properties"], dict):
        raise ValueError(f"inputSchema missing valid 'properties' field: {mcp_tool.name}")

    return True

def convert_schema_to_pydantic(schema: dict) -> type[BaseModel]:
    """
    将 MCP 的 JSON Schema 转为 LangChain 的 Pydantic Model
    """
    fields = {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for field_name, field_info in properties.items():
        field_type = str
        default = ... if field_name in required else None
        fields[field_name] = (field_type, default)

    return create_model("ToolArgs", **fields)

def mcp_tool_to_langchain_tool(
    mcp_tool: types.Tool,
    mcp_client: MCPClient
) -> BaseTool:
    validate_mcp_tool(mcp_tool)
    args_schema = convert_schema_to_pydantic(mcp_tool.inputSchema)

    async def async_func(**kwargs):
        result = await mcp_client.use_tool(mcp_tool.name, kwargs)
        return result.content[0].text

    return Tool(
        name=mcp_tool.name,
        description=mcp_tool.description,
        func=lambda **kws: async_func(**kws),
        args_schema=args_schema,
        coroutine=async_func
    )

def convert_mcp_tools_to_langchain(
    mcp_tools: list[types.Tool],
    mcp_client: MCPClient
) -> list[BaseTool]:
    """批量转换"""

    return [mcp_tool_to_langchain_tool(t, mcp_client) for t in mcp_tools]
