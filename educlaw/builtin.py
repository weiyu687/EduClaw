"""Opt-in adapters reusing EduClaw's retrieval, document and Skill primitives."""
import hashlib
import sqlite3
from contextlib import contextmanager

from ._shared.retrieval import chunks, lexical_rank
from ._shared.skills import SkillRegistry
from .chat import setup_chat, check_session
from .plugins import Plugin


def setup_memory(ctx):
    app = ctx.application
    def reference(session, query):
        rows = list(reversed(app.state.list_runs(session)))
        rows = [r for r in rows if r["status"] == "completed"]
        recent = [{"user": r["input"][:1000], "assistant": (r["output"] or "")[:1000]} for r in rows[-4:]]
        candidates = [{"id": r["id"], "text": (r["input"] + "\n" + (r["output"] or ""))[:1800]} for r in rows[:-4]]
        return {"recent": recent, "recall": lexical_rank(query, candidates, 2)} if rows else None
    ctx.context(reference)


def setup_skills(ctx):
    # Only the explicitly configured application Skill directory, never platform skills.
    root = ctx.path(ctx.config["directory"]) if "directory" in ctx.config else ctx.data_dir / "skills"
    registry = SkillRegistry(root)
    selected = ctx.config.get("selected", [])
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
        raise ValueError("skills.selected must be a list of IDs.")
    def reference(session, query):
        return [{"id": name, "guidance": registry.load(name)[:6000]} for name in selected]
    ctx.context(reference)
    ctx.operation("list", registry.list, description="Browse application Skills")
    ctx.operation("read", lambda skill_id: {"id": skill_id, "content": registry.load(skill_id)})


def setup_tools(ctx):
    allowed = ctx.config.get("allow", [])
    if not isinstance(allowed, list) or any(not isinstance(x, str) for x in allowed):
        raise ValueError("tools.allow must be an explicit list of tool names.")
    ctx.operation("list", lambda: [t.specification() for t in ctx.application.tools().values()])


def setup_knowledge(ctx):
    app = ctx.application
    path = ctx.data_dir / "knowledge.sqlite3"
    @contextmanager
    def database():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    with database() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT NOT NULL,text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS mounts(session TEXT,document TEXT,PRIMARY KEY(session,document));
        """)
    def add(session, name, text):
        check_session(app, session)
        if not isinstance(text, str) or not 1 <= len(text) <= 100000 or not isinstance(name, str) or not 1 <= len(name) <= 180:
            raise ValueError("Document requires a name (1..180) and text (1..100000 characters).")
        did = hashlib.sha256((name + "\0" + text).encode()).hexdigest()
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM documents WHERE id=?", (did,)).fetchone():
                if db.execute("SELECT coalesce(sum(length(text)),0) FROM documents").fetchone()[0] + len(text) > 3000000:
                    raise ValueError("Application knowledge quota exceeded (3 million characters).")
                db.execute("INSERT INTO documents VALUES(?,?,?)", (did, name, text))
            db.execute("INSERT OR IGNORE INTO mounts VALUES(?,?)", (session, did))
        return {"id": did}
    def mount(session, document, enabled):
        check_session(app, session)
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        with database() as db:
            if not db.execute("SELECT 1 FROM documents WHERE id=?", (document,)).fetchone():
                raise LookupError("Document not found.")
            if enabled:
                db.execute("INSERT OR IGNORE INTO mounts VALUES(?,?)", (session, document))
            else:
                db.execute("DELETE FROM mounts WHERE session=? AND document=?", (session, document))
        return {"id": document, "enabled": enabled}
    def search(session, query):
        check_session(app, session)
        if not isinstance(query, str) or not 1 <= len(query) <= 4000:
            raise ValueError("Query must contain 1..4000 characters.")
        with database() as db:
            rows = db.execute("SELECT d.* FROM documents d JOIN mounts m ON d.id=m.document WHERE m.session=?", (session,)).fetchall()
        parts = [{"id": row["id"] + ":" + str(i), "name": row["name"], "text": part}
                 for row in rows for i, part in enumerate(chunks(row["text"]))]
        return lexical_rank(query, parts, 4)
    def documents(session):
        check_session(app, session)
        with database() as db:
            return [dict(r) for r in db.execute("SELECT d.id,d.name FROM documents d JOIN mounts m ON d.id=m.document WHERE m.session=?", (session,))]
    ctx.operation("add", add, description="Add and mount application text knowledge")
    ctx.operation("mount", mount, description="Enable or disable a document for a session")
    ctx.operation("search", search, description="Search mounted documents with local BM25")
    ctx.operation("list", documents)
    ctx.context(search)


def builtins():
    return [Plugin("chat", setup_chat), Plugin("memory", setup_memory, ("chat",)),
            Plugin("skills", setup_skills, ("chat",)), Plugin("knowledge", setup_knowledge, ("chat",)),
            Plugin("tools", setup_tools, ("chat",))]
