"""Independent apps, plugin enforcement, durable agent execution and HTTP."""
import asyncio
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from educlaw import AppConfig, Application, CapabilityDisabled, Plugin, Tool
from educlaw.cli import scaffold
from educlaw.http import ApplicationServer
from educlaw.models import OpenAICompatibleModel


class Model:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def complete(self, messages, tools):
        self.requests.append((messages.copy(), tools))
        return self.responses.pop(0) if self.responses else {"content": "answer"}


def config(tmp_path, name="sample", plugins=("chat",), **kwargs):
    return AppConfig(name, tmp_path / name, plugins, **kwargs)


def run(value):
    return asyncio.run(value)


def session(app):
    return run(app.invoke("chat.create_session"))["session"]


def call(name="double", args='{"value": 3}'):
    return {"id": "call-1", "type": "function", "function": {"name": name, "arguments": args}}


def calculator(seen):
    def setup(ctx):
        def double(value):
            seen.append(value)
            return value * 2
        ctx.tool(Tool("double", "Double a number", double, {
            "type": "object", "properties": {"value": {"type": "integer", "minimum": 0}},
            "required": ["value"], "additionalProperties": False}))
        ctx.operation("ping", lambda: {"app": ctx.application.config.app_id})
    return Plugin("calculator", setup)


def test_two_apps_same_session_id_have_separate_history_memory_knowledge_events(tmp_path):
    models = [Model(), Model()]
    with Application(config(tmp_path, "alpha", ("chat", "memory", "knowledge")), model=models[0]) as a, \
         Application(config(tmp_path, "beta", ("chat", "memory", "knowledge")), model=models[1]) as b:
        for app in (a, b):
            app.state.ensure_session("shared-session-id")
        run(a.invoke("knowledge.add", {"session": "shared-session-id", "name": "private", "text": "ALPHA_SECRET budget 742"}))
        result = run(a.chat("shared-session-id", "ALPHA_SECRET"))
        run(b.chat("shared-session-id", "ALPHA_SECRET"))
        assert "budget 742" in json.dumps(models[0].requests)
        assert "budget 742" not in json.dumps(models[1].requests)
        assert run(b.invoke("knowledge.search", {"session": "shared-session-id", "query": "budget"})) == []
        with pytest.raises(LookupError):
            run(b.invoke("chat.events", {"run_id": result["run_id"]}))
        a.business_dir.joinpath("orders.json").write_text("private")
        assert not b.business_dir.joinpath("orders.json").exists()
        assert len(run(a.invoke("chat.history", {"session": "shared-session-id"}))) == 1
        assert a.state.path != b.state.path


def test_disabled_memory_and_knowledge_do_not_inject_data(tmp_path):
    model = Model()
    cfg = config(tmp_path, plugins=("chat", "memory", "knowledge"))
    with Application(cfg, model=model) as app:
        sid = session(app)
        run(app.chat(sid, "PRIVATE_HISTORY"))
        run(app.invoke("knowledge.add", {"session": sid, "name": "note", "text": "PRIVATE_DOCUMENT budget"}))
        app.set_enabled("memory", False)
        app.set_enabled("knowledge", False)
        run(app.chat(sid, "budget"))
        assert "PRIVATE_HISTORY" not in json.dumps(model.requests[-1])
        assert "PRIVATE_DOCUMENT" not in json.dumps(model.requests[-1])
        with pytest.raises(CapabilityDisabled):
            run(app.invoke("knowledge.search", {"session": sid, "query": "budget"}))
        app.set_enabled("knowledge", True)
        assert run(app.invoke("knowledge.search", {"session": sid, "query": "budget"}))


def test_plugin_tool_execution_events_and_idempotency(tmp_path):
    seen = []
    model = Model({"tool_calls": [call()]}, {"content": "6"})
    cfg = config(tmp_path, plugins=("calculator", "tools", "chat"), options={"tools": {"allow": ["double"]}})
    with Application(cfg, model=model, plugins=[calculator(seen)]) as app:
        sid = session(app)
        result = run(app.chat(sid, "double 3", request_id="request-1234567890"))
        repeated = run(app.chat(sid, "double 3", request_id="request-1234567890"))
        assert repeated["reused"] and result["run_id"] == repeated["run_id"]
        assert seen == [3] and result["answer"] == "6"
        events = run(app.invoke("chat.events", {"run_id": result["run_id"]}))
        assert next(e for e in events if e["kind"] == "tool.completed")["payload"]["output"] == 6
        with pytest.raises(PermissionError):
            run(app.chat(sid, "different", request_id="request-1234567890"))
        app.set_enabled("calculator", False)
        assert app.tools() == {}
        with pytest.raises(CapabilityDisabled):
            run(app.invoke("calculator.ping"))


@pytest.mark.parametrize("plugins,allowed", [(("chat", "calculator"), ["double"]), (("chat", "tools", "calculator"), [])])
def test_model_cannot_call_disabled_or_unallowlisted_tool(tmp_path, plugins, allowed):
    seen = []
    with Application(config(tmp_path, plugins=plugins, options={"tools": {"allow": allowed}}),
                     model=Model({"tool_calls": [call()]}), plugins=[calculator(seen)]) as app:
        sid = session(app)
        with pytest.raises(CapabilityDisabled):
            run(app.chat(sid, "do it", request_id="request-1234567890"))
        assert seen == []
        assert run(app.invoke("chat.history", {"session": sid}))[0]["status"] == "failed"
        with pytest.raises(RuntimeError):
            run(app.chat(sid, "do it", request_id="request-1234567890"))


@pytest.mark.parametrize("args", ['{"value": true}', '{"value": -1}', '{"value": 3,"extra":4}', '{}'])
def test_invalid_tool_arguments_never_execute(tmp_path, args):
    seen = []
    with Application(config(tmp_path, plugins=("chat", "tools", "calculator"), options={"tools": {"allow": ["double"]}}),
                     model=Model({"tool_calls": [call(args=args)]}), plugins=[calculator(seen)]) as app:
        with pytest.raises(ValueError):
            run(app.chat(session(app), "invalid args"))
        assert seen == []


def test_batch_validation_happens_before_any_tool_side_effect(tmp_path):
    seen = []
    invalid = call("forbidden")
    invalid["id"] = "call-2"
    with Application(config(tmp_path, plugins=("chat", "tools", "calculator"), options={"tools": {"allow": ["double"]}}),
                     model=Model({"tool_calls": [call(), invalid]}), plugins=[calculator(seen)]) as app:
        with pytest.raises(CapabilityDisabled):
            run(app.chat(session(app), "batch"))
        assert not seen


def test_app_root_ownership_and_process_lock(tmp_path):
    cfg = config(tmp_path)
    with Application(cfg):
        with pytest.raises(RuntimeError, match="Another runtime"):
            Application(cfg)
        with pytest.raises(ValueError, match="nested"):
            Application(AppConfig("child", cfg.data_dir / "child"))
    with pytest.raises(ValueError, match="different app"):
        Application(AppConfig("other", cfg.data_dir))
    with Application(cfg):
        pass
    existing = tmp_path / "platform-data"
    existing.mkdir()
    (existing / "private.sqlite3").write_text("existing platform data")
    with pytest.raises(ValueError, match="nonempty"):
        Application(AppConfig("sample", existing))
    assert (existing / "private.sqlite3").read_text() == "existing platform data"


def test_plugin_dependency_cycle_and_rollback(tmp_path):
    with pytest.raises(ValueError, match="dependencies"):
        Application(config(tmp_path, plugins=("memory",)))
    order = []
    good = Plugin("good", lambda ctx: (order.append("start") or (lambda: order.append("stop"))))
    def fail(ctx):
        ctx.operation("partial", lambda: None)
        raise ValueError("startup failure")
    with pytest.raises(ValueError, match="startup failure"):
        Application(config(tmp_path, plugins=("good", "bad")), plugins=[good, Plugin("bad", fail)])
    assert order == ["start", "stop"]
    with Application(config(tmp_path)) as app:
        app.set_enabled("memory", True)
        with pytest.raises(ValueError, match="dependents"):
            app.set_enabled("chat", False)


def test_disabled_extension_is_not_imported(tmp_path):
    with Application(config(tmp_path, extensions={"external": "does_not_exist:plugin"})) as app:
        assert not app.enabled("external")
        with pytest.raises(ModuleNotFoundError):
            app.set_enabled("external", True)
        assert not app.enabled("external")


def test_failed_setup_unregisters_partial_operations(tmp_path):
    def fail(ctx):
        ctx.operation("partial", lambda: "should not exist")
        raise ValueError("failure")
    with Application(config(tmp_path), plugins=[Plugin("broken", fail)]) as app:
        with pytest.raises(ValueError):
            app.set_enabled("broken", True)
        with pytest.raises(CapabilityDisabled):
            run(app.invoke("broken.partial"))


def test_config_paths_relative_to_manifest_and_no_dotenv(tmp_path, monkeypatch):
    root = scaffold(tmp_path / "standalone", "standalone", ("chat", "knowledge"))
    (root / ".env").write_text("EDUCLAW_MODEL_API_KEY=NEVER_IMPORT_THIS\n")
    monkeypatch.delenv("EDUCLAW_MODEL_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    import os
    with Application.load(root / "app.toml") as app:
        assert app.data_dir == root / ".app-data"
        assert "EDUCLAW_MODEL_API_KEY" not in os.environ
        assert run(app.chat(session(app), "hello"))["answer"] == "[offline demo] hello"
    with pytest.raises(FileExistsError):
        scaffold(root, "standalone")


def test_skill_context_uses_only_app_directory(tmp_path):
    skill = tmp_path / "custom-skills" / "writing"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: writing\n---\nAPP_SKILL_ONLY", encoding="utf-8")
    model = Model()
    with Application(config(tmp_path, plugins=("chat", "skills"),
                            options={"skills": {"directory": str(skill.parent), "selected": ["writing"]}}), model=model) as app:
        assert [s["id"] for s in run(app.invoke("skills.list"))] == ["writing"]
        sid = session(app)
        run(app.chat(sid, "hi"))
        assert "APP_SKILL_ONLY" in json.dumps(model.requests[-1])
        app.set_enabled("skills", False)
        run(app.chat(sid, "hi"))
        assert "APP_SKILL_ONLY" not in json.dumps(model.requests[-1])


def test_busy_session_and_plugin_switch_and_cancellation(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            async def complete(self, messages, tools):
                entered.set()
                await release.wait()
                return {"content": "done"}
        with Application(config(tmp_path), model=Slow()) as app:
            sid = (await app.invoke("chat.create_session"))["session"]
            task = asyncio.create_task(app.chat(sid, "first"))
            await entered.wait()
            with pytest.raises(RuntimeError, match="active run"):
                await app.chat(sid, "second")
            with pytest.raises(RuntimeError, match="active operations"):
                app.set_enabled("memory", True)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (await app.invoke("chat.history", {"session": sid}))[0]["status"] == "interrupted"
            release.set()
            assert (await app.chat(sid, "third"))["answer"] == "done"
    run(scenario())


def test_restart_persists_history_and_recovers_abandoned_run(tmp_path):
    cfg = config(tmp_path)
    with Application(cfg, model=Model()) as app:
        sid = session(app)
        first = run(app.chat(sid, "persist", request_id="request-1234567890"))
        abandoned = app.state.start_run(sid, "abandoned")
    with Application(cfg, model=Model()) as app:
        assert run(app.chat(sid, "persist", request_id="request-1234567890"))["run_id"] == first["run_id"]
        assert next(r for r in app.state.list_runs(sid) if r["id"] == abandoned)["status"] == "interrupted"


def test_max_rounds_prevents_unbounded_tool_execution(tmp_path):
    seen = []
    cfg = config(tmp_path, plugins=("chat", "tools", "calculator"),
                 options={"tools": {"allow": ["double"]}, "chat": {"max_rounds": 1}})
    with Application(cfg, model=Model({"tool_calls": [call()]}), plugins=[calculator(seen)]) as app:
        with pytest.raises(RuntimeError, match="max_rounds"):
            run(app.chat(session(app), "loop"))
        assert seen == [3]


def test_real_http_auth_cors_capabilities_and_independent_sessions(tmp_path):
    token = "t" * 40
    with Application(config(tmp_path), model=Model()) as app:
        with ApplicationServer(app, token=token, origins=["http://localhost:5173"]) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def request(path, data=None, headers=None):
                req = Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                              headers=headers if headers is not None else {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                try:
                    with urlopen(req) as response:
                        return response.status, json.load(response), dict(response.headers)
                except HTTPError as error:
                    return error.code, json.load(error), dict(error.headers)
            try:
                assert request("/v1/app", headers={})[0] == 401
                assert request("/v1/app", headers={"Authorization": "Bearer " + token, "Origin": "http://evil.invalid"})[0] == 403
                status, capabilities, headers = request("/v1/app", headers={"Authorization": "Bearer " + token, "Origin": "http://localhost:5173"})
                assert status == 200 and headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
                assert "state.sqlite3" not in json.dumps(capabilities)
                sid = request("/v1/operations/chat.create_session", {})[1]["result"]["session"]
                response = request("/v1/operations/chat.send", {"session": sid, "message": "hello"})
                assert response[0] == 200 and response[1]["result"]["answer"] == "answer"
                assert request("/v1/operations/knowledge.search", {"session": sid, "query": "x"})[0] == 403
                assert request("/v1/operations/chat.send", ["wrong"])[0] == 400
                assert request("/v1/operations/chat.send", {"session": "other-app-id", "message": "x"})[0] == 404
                assert request("/v1/app?token=" + token)[0] == 400
            finally:
                server.shutdown()
                thread.join()


def test_provider_uses_explicit_app_credential_and_real_http(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    captured = []
    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append((self.path, self.headers["Authorization"], json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            data = json.dumps({"choices": [{"message": {"role": "assistant", "content": "provider answer"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *_):
            pass
    monkeypatch.setenv("TEST_APP_KEY", "application-key")
    monkeypatch.setenv("EDUCLAW_MODEL_API_KEY", "platform-key")
    with HTTPServer(("127.0.0.1", 0), Provider) as server:
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            model = OpenAICompatibleModel(name="test", base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key_env="TEST_APP_KEY")
            with Application(config(tmp_path), model=model) as app:
                assert run(app.chat(session(app), "hello"))["answer"] == "provider answer"
            assert captured[0][0] == "/v1/chat/completions"
            assert captured[0][1] == "Bearer application-key"
            assert "platform-key" not in json.dumps(captured)
        finally:
            server.shutdown()
            worker.join()


def test_pure_business_app_needs_no_chat_or_model(tmp_path):
    plugin = Plugin("business", lambda ctx: ctx.operation("ping", lambda: {"ok": True}))
    with Application(config(tmp_path, plugins=("business",)), plugins=[plugin]) as app:
        assert run(app.invoke("business.ping")) == {"ok": True}
        assert app.tools() == {}
        with pytest.raises(CapabilityDisabled):
            run(app.chat("session", "hello"))


def test_knowledge_mount_is_session_scoped_and_persistent(tmp_path):
    cfg = config(tmp_path, plugins=("chat", "knowledge"))
    with Application(cfg) as app:
        first, second = session(app), session(app)
        doc = run(app.invoke("knowledge.add", {"session": first, "name": "private", "text": "ALPHA_BUDGET_742"}))["id"]
        assert run(app.invoke("knowledge.search", {"session": second, "query": "ALPHA_BUDGET_742"})) == []
        run(app.invoke("knowledge.mount", {"session": first, "document": doc, "enabled": False}))
        assert run(app.invoke("knowledge.search", {"session": first, "query": "ALPHA_BUDGET_742"})) == []
    with Application(cfg) as app:
        run(app.invoke("knowledge.mount", {"session": second, "document": doc, "enabled": True}))
        assert run(app.invoke("knowledge.search", {"session": second, "query": "ALPHA_BUDGET_742"}))


def test_unsupported_tool_schema_fails_registration(tmp_path):
    def setup(ctx):
        ctx.tool(Tool("unsupported", "bad schema", lambda: None, {"type": "object", "$ref": "external"}))
    with pytest.raises(ValueError, match="unsupported"):
        Application(config(tmp_path, plugins=("invalid",)), plugins=[Plugin("invalid", setup)])


def test_provider_does_not_forward_secret_on_redirect(monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    received = []
    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/should-not-follow")
            self.send_header("Content-Length", "0")
            self.end_headers()
        def do_GET(self):
            received.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
        def log_message(self, *_):
            pass
    monkeypatch.setenv("REDIRECT_TEST_KEY", "do-not-forward")
    with HTTPServer(("127.0.0.1", 0), Redirect) as server:
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            model = OpenAICompatibleModel(name="test", base_url=f"http://127.0.0.1:{server.server_port}", api_key_env="REDIRECT_TEST_KEY")
            with pytest.raises(HTTPError) as error:
                run(model.complete([{"role": "user", "content": "test"}], []))
            assert error.value.code == 302
            assert received == []
        finally:
            server.shutdown()
            worker.join()
