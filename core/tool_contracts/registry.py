"""Versioned contracts with explicit adapter binding and bounded results.

Only application-owned manifests are loaded. Registration is code installation,
not user approval; path and execution grants still belong to the gateway.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


class ContractError(ValueError):
    category = 'schema_error'
    uncertain = True


class ToolRegistry:
    def __init__(self, manifests):
        self._items = {}
        for source in manifests:
            item = deepcopy(source)
            name = item.get('name')
            if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name):
                raise ValueError('Invalid tool name')
            if name in self._items:
                raise ValueError('Duplicate tool contract: ' + name)
            if type(item.get('sdk_version')) is not int or item['sdk_version'] != 1:
                raise ValueError('Unsupported tool SDK version')
            if not re.fullmatch(r'\d+\.\d+\.\d+', item.get('version', '')):
                raise ValueError('Invalid tool version')
            if item.get('adapter') != name:
                raise ValueError('Adapter must be explicitly bound by tool name')
            if item.get('risk') not in ('path_read', 'public_read', 'code_execute', 'denied'):
                raise ValueError('Unknown risk class')
            if item.get('output_encoding') not in ('text', 'json'):
                raise ValueError('Unknown output encoding')
            if type(item.get('max_output_bytes')) is not int or not 1 <= item['max_output_bytes'] <= 2000000:
                raise ValueError('Invalid result limit')
            for key in ('inputSchema', 'output_schema'):
                schema = item.get(key)
                if not isinstance(schema, dict):
                    raise ValueError('Missing contract schema')
                # Contracts must be self-contained: never resolve remote references.
                def check(value):
                    if isinstance(value, dict):
                        if any(k in value for k in ('$ref', '$dynamicRef')):
                            raise ValueError('Schema references are not supported')
                        for nested in value.values(): check(nested)
                    elif isinstance(value, list):
                        for nested in value: check(nested)
                check(schema)
                Draft202012Validator.check_schema(schema)
            if item['inputSchema'].get('type') != 'object':
                raise ValueError('Input schema must be an object')
            if item['risk'] == 'path_read':
                field = item.get('resource_argument')
                if (field not in item['inputSchema'].get('required', []) or
                        item['inputSchema'].get('properties', {}).get(field, {}).get('type') != 'string'):
                    raise ValueError('Read contract must declare a required path')
            if item.get('plannable') and item['risk'] not in ('path_read', 'code_execute'):
                raise ValueError('No planning adapter for this risk class')
            item['digest'] = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            self._items[name] = item

    def get(self, name):
        if name not in self._items:
            raise PermissionError('Tool has no trusted contract: ' + str(name))
        return deepcopy(self._items[name])

    def items(self):
        return [self.get(name) for name in self._items]

    def validate_input(self, name, arguments):
        errors = list(Draft202012Validator(self.get(name)['inputSchema']).iter_errors(arguments))
        if errors:
            # Do not include input values (paths, code or secrets) in error messages.
            raise ContractError('Tool input does not satisfy its registered schema: ' + name)

    def validate_result(self, name, result):
        item = self.get(name)
        if not isinstance(result, str) or len(result.encode('utf-8')) > item['max_output_bytes']:
            raise ContractError('Tool result type or size exceeds contract: ' + name)
        try:
            value = json.loads(result) if item['output_encoding'] == 'json' else result
        except ValueError as exc:
            raise ContractError('Tool result is not valid JSON: ' + name) from exc
        if not Draft202012Validator(item['output_schema']).is_valid(value):
            raise ContractError('Tool result does not satisfy registered schema: ' + name)
        return value

    def health(self, adapters):
        return [dict(name=x['name'], version=x['version'], digest=x['digest'], risk=x['risk'],
                     status='ready' if callable(adapters.get(x['adapter'])) else 'adapter_missing')
                for x in self.items()]

    def descriptors(self):
        import mcp.types as types
        return [types.Tool(name=x['name'], description=x['description'], inputSchema=x['inputSchema'],
                           outputSchema=x['output_schema'] if x['output_encoding'] == 'json' else None,
                           _meta={'educlaw':{k:x[k] for k in ('version','sdk_version','digest','risk','resource_argument')}})
                for x in self.items()]

    async def invoke(self, name, arguments, adapters):
        from core.security.tool_cancellation import run_sync
        item = self.get(name)
        self.validate_input(name, arguments)
        adapter = adapters.get(item['adapter'])
        if not callable(adapter):
            raise PermissionError('Registered tool adapter is unavailable: ' + name)
        result = await run_sync(adapter, arguments)
        return self.validate_result(name, result)


@lru_cache(maxsize=1)
def builtin_registry():
    return ToolRegistry(json.loads(Path(__file__).with_name('builtin.json').read_text(encoding='utf-8')))
