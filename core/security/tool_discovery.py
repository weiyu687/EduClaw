"""MCP metadata synchronization; never executes or authorizes tools."""
from core.security.tool_onboarding import record_discovered


async def sync_client(client, server=None):
    """Fetch tool descriptors from a connected MCP client and record metadata.

    A failed scan does not change the registry or relax the security gateway.
    """
    source = server or getattr(client, "server_script", None) or "local-mcp"
    tools = await client.get_tools()
    result = {"seen": 0, "new_or_changed": 0, "unchanged": 0, "errors": []}
    for tool in tools:
        try:
            name = getattr(tool, "name", None)
            description = getattr(tool, "description", "")
            schema = getattr(tool, "inputSchema", None)
            if schema is None:
                schema = getattr(tool, "input_schema", None)
            recorded = record_discovered(source, name, description, schema)
            result["seen"] += 1
            if recorded["changed"]:
                result["new_or_changed"] += 1
            else:
                result["unchanged"] += 1
        except (ValueError, TypeError) as exc:
            result["errors"].append(str(exc))
    return result
