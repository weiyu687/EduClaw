"""Small plugin contract. Python plugins are trusted application code."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False})

    def specification(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


@dataclass(frozen=True)
class Plugin:
    name: str
    setup: Callable
    requires: tuple[str, ...] = ()
    api_version: int = 1


class PluginContext:
    """Resources scoped to one app and plugin; no platform singleton registry."""
    def __init__(self, application, name):
        self.application = application
        self.name = name
        self.config = dict(application.config.options.get(name, {}))
        self.data_dir = application.data_dir / "plugins" / name
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def operation(self, name, handler, *, description=""):
        self.application._register_operation(self.name, name, handler, description)

    def context(self, provider):
        """provider(session, query) -> JSON-safe untrusted reference data."""
        self.application._contexts[self.name] = provider

    def tool(self, tool: Tool):
        self.application._register_tool(self.name, tool)

    def path(self, value) -> Path:
        return self.application.config.resolve(value)
