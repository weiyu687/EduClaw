"""Run with the clean venv's Python, against its installed wheel, not source.

Usage: python -I scripts/runtime_e2e.py --example examples/standalone-agent --work <new-dir> --report <json>
Only a local deterministic model fixture is used; this is not a live LLM quality test.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import educlaw


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = payload["messages"]
        if messages[-1]["role"] == "tool":
            answer = {"role": "assistant", "content": messages[-1]["content"]}
        else:
            answer = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "fixture-call", "type": "function", "function": {
                    "name": "find_note", "arguments": json.dumps({"query": "budget"})}}]}
        body = json.dumps({"choices": [{"message": answer}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start(directory, environment):
    process = subprocess.Popen([sys.executable, "-E", "-s", "-B", str(directory / "main.py")],
                               cwd=directory.parent, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8",
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(lambda: [process.stdout.readline().strip() for _ in range(3)])
        try:
            lines = future.result(timeout=20)
        except BaseException:
            process.kill()
            raise
    if len(lines) != 3 or not lines[1].startswith("Address: ") or not lines[2].startswith("Bearer token: "):
        process.kill()
        raise RuntimeError("App did not start: " + process.stderr.read()[:2000])
    return process, lines[1].split(": ", 1)[1], lines[2].split(": ", 1)[1]


def request(app, operation, args):
    _, base, token = app
    req = Request(base + "/v1/operations/" + operation,
                  data=json.dumps(args).encode(), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urlopen(req, timeout=20) as response:
        return json.load(response)["result"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    # This process is launched with -I: no repository or user site packages.
    assert "site-packages" in educlaw.__file__, educlaw.__file__
    assert "langchain" not in sys.modules and "dotenv" not in sys.modules
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH" and not k.startswith("EDUCLAW_")}
    environment["E2E_APP_KEY"] = "local-fixture-not-a-real-key"
    applications = []
    checks = []
    with ThreadingHTTPServer(("127.0.0.1", 0), Provider) as provider:
        thread = threading.Thread(target=provider.serve_forever)
        thread.start()
        try:
            for name in ("app-a", "app-b"):
                target = args.work / name
                shutil.copytree(args.example, target, ignore=shutil.ignore_patterns(".app-data", "__pycache__"))
                manifest = target / "app.toml"
                text = manifest.read_text(encoding="utf-8").replace('id = "independent-notes"', f'id = "{name}"')
                text = text.replace('provider = "demo"', f'provider = "openai-compatible"\nname = "local-fixture"\nbase_url = "http://127.0.0.1:{provider.server_port}/v1"\napi_key_env = "E2E_APP_KEY"', 1)
                manifest.write_text(text, encoding="utf-8")
                applications.append(start(target, environment))
            a, b = applications
            sa = request(a, "chat.create_session", {})["session"]
            sb = request(b, "chat.create_session", {})["session"]
            request(a, "notes.add", {"title": "budget", "body": "APP_A_PRIVATE_742"})
            request(b, "notes.add", {"title": "budget", "body": "APP_B_PRIVATE_853"})
            checks.append("two_standalone_processes")
            with ThreadPoolExecutor(2) as pool:
                fa = pool.submit(request, a, "chat.send", {"session": sa, "message": "budget", "request_id": "same-request-123456789"})
                fb = pool.submit(request, b, "chat.send", {"session": sb, "message": "budget", "request_id": "same-request-123456789"})
                ra, rb = fa.result(), fb.result()
            assert "APP_A_PRIVATE_742" in ra["answer"] and "APP_B_PRIVATE_853" not in ra["answer"]
            assert "APP_B_PRIVATE_853" in rb["answer"] and "APP_A_PRIVATE_742" not in rb["answer"]
            checks.append("concurrent_model_tool_business_data_isolation")
            try:
                request(b, "chat.history", {"session": sa})
                raise AssertionError("Cross-app session unexpectedly accessible")
            except HTTPError as error:
                assert error.code == 404
            checks.append("cross_app_session_denied")
            events = request(a, "chat.events", {"run_id": ra["run_id"]})
            assert [e["kind"] for e in events] == ["run.started", "model.started", "model.completed", "tool.started", "tool.completed", "model.started", "model.completed", "run.completed"]
            checks.append("real_http_model_tool_events")
            a[0].terminate()
            a[0].wait(timeout=10)
            restarted = start(args.work / "app-a", environment)
            applications.append(restarted)
            replay = request(restarted, "chat.send", {"session": sa, "message": "budget", "request_id": "same-request-123456789"})
            assert replay["reused"] and replay["run_id"] == ra["run_id"]
            checks.append("restart_persistence_and_no_replay")
            report = {"runtime_version": educlaw.__version__, "installed_module": educlaw.__file__,
                      "python": sys.version.split()[0], "model": "local deterministic OpenAI-compatible fixture",
                      "checks": checks, "passed": True}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
        finally:
            for app in applications:
                process = app[0]
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            provider.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
