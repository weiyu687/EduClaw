"""Read-only catalog diagnostics shared by CLI and future local UI."""
from core.tool_contracts import builtin_registry


async def inspect_tools(client):
    descriptors = await client.get_tools()
    from core.security.dynamic_permissions import enforcement_mode
    rows = []
    for contract in builtin_registry().items():
        matches = [x for x in descriptors if x.name == contract['name']]
        status = 'unavailable' if not matches else 'duplicate_name' if len(matches) != 1 else 'ready'
        if status == 'ready':
            remote = matches[0]
            metadata = getattr(remote, 'meta', None) or {}
            expected_output = contract['output_schema'] if contract['output_encoding'] == 'json' else None
            if (remote.inputSchema != contract['inputSchema'] or
                    getattr(remote, 'outputSchema', None) != expected_output or
                    metadata.get('educlaw', {}).get('digest') != contract['digest']):
                status = 'contract_mismatch'
        rows.append({'name':contract['name'], 'version':contract['version'], 'status':status,
                     'risk':contract['risk'], 'resource_argument':contract['resource_argument'],
                     'permission':enforcement_mode(contract['name']), 'digest':contract['digest']})
    return rows


async def render_tools(client):
    rows = await inspect_tools(client)
    return '\n'.join(['工具契约检查（仅检查连接、声明与权限，不执行工具）：'] +
        [f"{r['name']} v{r['version']} | {r['status']} | {r['risk']} | 权限 {r['permission']}"
         for r in rows])
