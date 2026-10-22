"""Explicit application configuration; no ambient .env or cwd defaults."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise ValueError("Identifiers must use lowercase letters, digits, '_' or '-'.")
    return value


@dataclass(frozen=True)
class AppConfig:
    app_id: str
    data_dir: Path
    plugins: tuple[str, ...] = ("chat",)
    options: dict = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    extensions: dict = field(default_factory=dict)
    base_dir: Path = field(default_factory=Path.cwd)
    system_prompt: str = "You are a helpful assistant. Use only available tools."

    def __post_init__(self):
        identifier(self.app_id)
        if len(set(self.plugins)) != len(self.plugins):
            raise ValueError("Duplicate enabled plugin.")
        for name in self.plugins:
            identifier(name)
        object.__setattr__(self, "base_dir", Path(self.base_dir).resolve())
        object.__setattr__(self, "data_dir", self.resolve(self.data_dir))
        object.__setattr__(self, "plugins", tuple(self.plugins))

    def resolve(self, path):
        path = Path(path)
        return (path if path.is_absolute() else self.base_dir / path).resolve()

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        unknown = set(raw) - {"app", "plugins", "model", "extensions"}
        if unknown:
            raise ValueError(f"Unknown configuration sections: {sorted(unknown)}")
        app = dict(raw["app"])
        allowed = {"id", "data_dir", "plugins", "system_prompt"}
        if set(app) - allowed:
            raise ValueError("Unknown app configuration key.")
        return cls(app_id=app.pop("id"), data_dir=app.pop("data_dir"),
                   options=raw.get("plugins", {}), model=raw.get("model", {}),
                   extensions=raw.get("extensions", {}), base_dir=path.parent, **app)
