"""Business data is separate from both agent state and platform data."""
from contextlib import closing
import sqlite3
import uuid

from educlaw import Plugin, Tool


def setup(ctx):
    path = ctx.application.business_dir / "notes.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,title TEXT,body TEXT)")

    def add(title, body):
        if not isinstance(title, str) or not 1 <= len(title) <= 180:
            raise ValueError("title must contain 1..180 characters")
        if not isinstance(body, str) or not 1 <= len(body) <= 20000:
            raise ValueError("body must contain 1..20000 characters")
        note_id = uuid.uuid4().hex
        with closing(sqlite3.connect(path)) as db:
            with db:
                db.execute("INSERT INTO notes VALUES(?,?,?)", (note_id, title, body))
        return {"id": note_id, "title": title}

    def find(query):
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise ValueError("query must contain 1..200 characters")
        with closing(sqlite3.connect(path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute(
                "SELECT id,title,substr(body,1,1000) AS excerpt FROM notes WHERE instr(title,?)>0 OR instr(body,?)>0 ORDER BY id LIMIT 5", (query, query))]

    ctx.operation("add", add, description="Save a note in this application's business database")
    ctx.operation("find", find, description="Search application notes")
    ctx.tool(Tool("find_note", "Read matching notes from the current application", find,
                  {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 200}},
                   "required": ["query"], "additionalProperties": False}))


plugin = Plugin("notes", setup)
