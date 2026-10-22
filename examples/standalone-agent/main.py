"""python main.py: no workbench, frontend build, or repository PYTHONPATH."""
from pathlib import Path
from educlaw.cli import serve

if __name__ == "__main__":
    serve(Path(__file__).with_name("app.toml"))
