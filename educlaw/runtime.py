"""Application composition, lifecycle and capability enforcement."""
import importlib
import inspect
import re
import threading

from ._shared.state import StateManager
from .config import AppConfig, identifier
from .plugins import Plugin, PluginContext
from .storage import ApplicationStorage


class CapabilityDisabled(PermissionError):
    pass


async def await_result(value):
    return await value if inspect.isawaitable(value) else value


class Application:
    def __init__(self, config: AppConfig, *, model=None, plugins=()):
        from .builtin import builtins
        self.config = config
        self.model = model
        self._registry = {p.name: p for p in builtins()}
        for plugin in plugins:
            if plugin.name in self._registry or plugin.name in config.extensions:
                raise ValueError(f"Duplicate plugin: {plugin.name}")
            self._registry[plugin.name] = plugin
        if set(config.extensions) & set(self._registry):
            raise ValueError("Extensions cannot replace built-in plugins.")
        self._operations, self._contexts, self._tools = {}, {}, {}
        self._enabled, self._cleanup = [], {}
        self._mutex = threading.RLock()
        self._calls = 0
        self._closed = False
        self.storage = ApplicationStorage(config.data_dir, config.app_id)
        self.data_dir = self.storage.root
        self.business_dir = self.storage.business_dir
        try:
            self.state = StateManager(self.storage.agent_dir / "state.sqlite3")
            self.state.mark_interrupted()
            pending = list(config.plugins)
            while pending:
                ready = [name for name in pending if all(dep in self._enabled for dep in self._plugin(name).requires)]
                if not ready:
                    raise ValueError(f"Missing or cyclic plugin dependencies: {pending}")
                for name in ready:
                    self.set_enabled(name, True)
                    pending.remove(name)
        except BaseException:
            self.close()
            raise

    @classmethod
    def load(cls, manifest, **kwargs):
        return cls(AppConfig.load(manifest), **kwargs)

    def _plugin(self, name):
        identifier(name)
        if name not in self._registry and name in self.config.extensions:
            target = self.config.extensions[name]
            if not isinstance(target, str) or target.count(":") != 1:
                raise ValueError("Extension must be an explicitly installed module:attribute.")
            module, attribute = target.split(":")
            self._registry[name] = getattr(importlib.import_module(module), attribute)
        plugin = self._registry.get(name)
        if not isinstance(plugin, Plugin) or plugin.name != name or plugin.api_version != 1:
            raise ValueError(f"Unknown or incompatible plugin: {name}")
        return plugin

    def _assert_open(self):
        if self._closed:
            raise RuntimeError("Application is closed.")

    def enabled(self, name):
        return name in self._enabled

    def require(self, name):
        self._assert_open()
        if not self.enabled(name):
            raise CapabilityDisabled(f"Plugin is disabled: {name}")

    def _unregister(self, name):
        self._operations = {k: v for k, v in self._operations.items() if v[0] != name}
        self._tools = {k: v for k, v in self._tools.items() if v[0] != name}
        self._contexts.pop(name, None)

    def set_enabled(self, name, enabled):
        """Change idle runtime only. Persist startup choices in the app manifest."""
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        with self._mutex:
            self._assert_open()
            if self._calls:
                raise RuntimeError("Wait for active operations before changing plugins.")
            if enabled == self.enabled(name):
                if enabled:
                    return
                if name not in self._registry and name not in self.config.extensions:
                    raise ValueError(f"Unknown plugin: {name}")
                return
            plugin = self._plugin(name)
            if enabled:
                missing = set(plugin.requires) - set(self._enabled)
                if missing:
                    raise ValueError(f"Enable dependencies first: {sorted(missing)}")
                try:
                    cleanup = plugin.setup(PluginContext(self, name))
                    if cleanup is not None and not callable(cleanup):
                        raise TypeError("Plugin setup must return None or a synchronous cleanup callable.")
                except BaseException:
                    self._unregister(name)
                    raise
                self._cleanup[name] = cleanup
                self._enabled.append(name)
            else:
                dependents = [p for p in self._enabled if name in self._plugin(p).requires]
                if dependents:
                    raise ValueError(f"Disable dependents first: {dependents}")
                self._unregister(name)
                self._enabled.remove(name)
                cleanup = self._cleanup.pop(name, None)
                if cleanup:
                    cleanup()

    def _register_operation(self, plugin, name, handler, description):
        identifier(name)
        key = f"{plugin}.{name}"
        if key in self._operations:
            raise ValueError(f"Duplicate operation: {key}")
        self._operations[key] = (plugin, handler, description)

    def _register_tool(self, plugin, tool):
        from .schema import check_schema
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", tool.name) or tool.name in self._tools:
            raise ValueError(f"Invalid or duplicate tool: {tool.name}")
        check_schema(tool.parameters)
        if tool.parameters["type"] != "object":
            raise ValueError("Tool arguments must have object schema.")
        self._tools[tool.name] = (plugin, tool)

    def tools(self):
        if not self.enabled("tools"):
            return {}
        allowed = self.config.options.get("tools", {}).get("allow", [])
        return {name: item[1] for name, item in self._tools.items() if name in allowed and self.enabled(item[0])}

    def capabilities(self):
        with self._mutex:
            return {"api_version": 1, "app_id": self.config.app_id,
                    "plugins": [{"name": name, "enabled": self.enabled(name)}
                                for name in sorted(set(self._registry) | set(self.config.extensions))],
                    "operations": [{"name": key, "description": value[2]} for key, value in sorted(self._operations.items())],
                    "tools": [tool.specification() for tool in self.tools().values()]}

    async def invoke(self, operation, arguments=None):
        if not isinstance(arguments, (dict, type(None))):
            raise ValueError("Operation arguments must be an object.")
        with self._mutex:
            self._assert_open()
            item = self._operations.get(operation)
            if item is None:
                raise CapabilityDisabled(f"Operation unavailable: {operation}")
            self._calls += 1
        try:
            inspect.signature(item[1]).bind(**(arguments or {}))
            return await await_result(item[1](**(arguments or {})))
        finally:
            with self._mutex:
                self._calls -= 1

    async def chat(self, session, message, *, request_id=None):
        return await self.invoke("chat.send", {"session": session, "message": message, "request_id": request_id})

    def close(self):
        with self._mutex:
            if self._closed:
                return
            if self._calls:
                raise RuntimeError("Wait for active operations before closing the app.")
            errors = []
            for name in reversed(self._enabled):
                try:
                    if self._cleanup.get(name):
                        self._cleanup[name]()
                except Exception as error:
                    errors.append(error)
            self._enabled.clear()
            self._operations.clear()
            self._contexts.clear()
            self._tools.clear()
            self.storage.close()
            self._closed = True
            if errors:
                raise ExceptionGroup("Plugin cleanup failed", errors)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
