"""Scaffold and run independent applications."""
import argparse
import json
from pathlib import Path
import secrets

from .config import identifier
from .runtime import Application


def scaffold(directory, app_id, enabled=("chat", "memory")):
    identifier(app_id)
    allowed = {"chat", "memory", "knowledge", "skills", "tools"}
    if set(enabled) - allowed or len(set(enabled)) != len(enabled):
        raise ValueError("Choose unique built-in plugin names.")
    if set(enabled) - {"chat"} and "chat" not in enabled:
        raise ValueError("These built-ins require chat.")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    manifest = f'''[app]
id = "{app_id}"
data_dir = "./.app-data"
plugins = {json.dumps(list(enabled))}
system_prompt = "You are the assistant for {app_id}."

# Offline transport to verify setup. Replace with your own model below.
[model]
provider = "demo"
# provider = "openai-compatible"
# name = "your-model"
# base_url = "https://your-provider.example/v1"
# api_key_env = "{app_id.upper().replace('-', '_')}_MODEL_KEY"

[plugins.tools]
allow = []

[plugins.skills]
directory = "./skills"
selected = []
'''
    (directory / "app.toml").write_text(manifest, encoding="utf-8")
    (directory / ".gitignore").write_text(".app-data/\n.env\n__pycache__/\n.venv/\n", encoding="utf-8")
    (directory / "skills").mkdir()
    (directory / "main.py").write_text('''"""Run from any working directory; the manifest owns all paths."""
from pathlib import Path
from educlaw.cli import serve

if __name__ == "__main__":
    serve(Path(__file__).with_name("app.toml"))
''', encoding="utf-8")
    (directory / "README.md").write_text(f'''# {app_id}

This application embeds educlaw-runtime and runs without the EduClaw workbench.

1. Install the local runtime wheel: `python -m pip install /path/to/educlaw_runtime-0.1.0-py3-none-any.whl`.
2. Run `python main.py`. Copy the printed local address and Bearer token into your own client.
3. POST `{{}}` to `/v1/operations/chat.create_session`, then POST
   `{{"session":"returned-id","message":"Hello"}}` to `/v1/operations/chat.send`.
   Send `Authorization: Bearer <token>` and `Content-Type: application/json`.

The default model is an explicitly labelled offline echo demo, not an LLM.
Edit app.toml and set the named environment variable to connect a real model.
The app never reads EduClaw's .env. Disable plugins by removing names from app.plugins.
The data, events and business directories live in .app-data beside this manifest.
No platform data is imported. For browser clients, start `python -m educlaw serve app.toml
--origin http://localhost:5173` to allow that exact frontend origin.
''', encoding="utf-8")
    return directory


def serve(manifest, *, port=0, origins=()):
    from .http import ApplicationServer
    token = secrets.token_urlsafe(32)
    with Application.load(manifest) as app:
        with ApplicationServer(app, token=token, port=port, origins=origins) as server:
            print(f"Application: {app.config.app_id}", flush=True)
            print(f"Address: http://127.0.0.1:{server.server_port}", flush=True)
            print(f"Bearer token: {token}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


def main():
    parser = argparse.ArgumentParser(prog="educlaw")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a standalone application")
    init.add_argument("directory")
    init.add_argument("--id", required=True)
    init.add_argument("--plugins", default="chat,memory")
    run = commands.add_parser("serve", help="Serve a local backend")
    run.add_argument("manifest")
    run.add_argument("--port", type=int, default=0)
    run.add_argument("--origin", action="append", default=[])
    show = commands.add_parser("inspect", help="Validate configuration and list enabled capabilities")
    show.add_argument("manifest")
    args = parser.parse_args()
    if args.command == "init":
        print(scaffold(args.directory, args.id, tuple(filter(None, args.plugins.split(",")))))
    elif args.command == "serve":
        serve(args.manifest, port=args.port, origins=args.origin)
    else:
        with Application.load(args.manifest) as app:
            print(json.dumps(app.capabilities(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
