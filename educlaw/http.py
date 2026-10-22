"""Optional authenticated loopback HTTP adapter; no frontend dependency."""
import asyncio
import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class ApplicationServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, app, *, token, host="127.0.0.1", port=0, origins=()):
        if host != "127.0.0.1":
            raise ValueError("This adapter supports loopback only; use a reviewed deployment adapter for remote access.")
        if not isinstance(token, str) or len(token) < 32 or not token.isascii():
            raise ValueError("HTTP token must be an ASCII secret of at least 32 characters.")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("CORS origins must be exact scheme://host[:port] values.")
        self.app, self.token, self.origins = app, token, frozenset(origins)
        super().__init__((host, port), ApplicationHandler)
        self.loop = asyncio.new_event_loop()
        self.worker = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.worker.start()

    def server_close(self):
        super().server_close()  # Wait for handler threads before releasing provider resources.
        if getattr(self, "worker", None) and self.worker.is_alive():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.worker.join()
            self.loop.close()


class ApplicationHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass  # Never emit authorization headers, prompts or query strings.

    def reply(self, status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin")
        if origin in self.server.origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, *, preflight=False):
        port = self.server.server_port
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self.reply(403, {"error": "invalid_host"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.origins:
            self.reply(403, {"error": "origin_denied"})
            return False
        if not preflight and not hmac.compare_digest(self.headers.get("Authorization", "").encode("utf-8"), ("Bearer " + self.server.token).encode("ascii")):
            self.reply(401, {"error": "unauthorized"})
            return False
        return True

    def do_OPTIONS(self):
        if self.allowed(preflight=True):
            self.reply(200, {"ok": True})

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        if not self.allowed():
            return
        try:
            route = urlsplit(self.path)
            if route.query:
                raise ValueError("Query parameters are unsupported.")
            if self.command == "GET" and route.path == "/v1/app":
                self.reply(200, self.server.app.capabilities())
                return
            if self.command == "GET" and route.path == "/health":
                self.reply(200, {"ok": True, "app_id": self.server.app.config.app_id})
                return
            if self.command != "POST" or not re.fullmatch(r"/v1/operations/[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*", route.path):
                self.reply(404, {"error": "not_found"})
                return
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked bodies are unsupported.")
            if self.headers.get_content_type() != "application/json":
                self.reply(415, {"error": "json_required"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                self.reply(413, {"error": "body_size"})
                return
            arguments = json.loads(self.rfile.read(length))
            operation = route.path.rsplit("/", 1)[-1]
            future = asyncio.run_coroutine_threadsafe(self.server.app.invoke(operation, arguments), self.server.loop)
            result = future.result()
            self.reply(200, {"result": result})
        except LookupError:
            self.reply(404, {"error": "not_found"})
        except PermissionError:
            self.reply(403, {"error": "capability_denied"})
        except (ValueError, TypeError):
            self.reply(400, {"error": "invalid_request"})
        except RuntimeError:
            self.reply(409, {"error": "operation_conflict"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply(502, {"error": "operation_failed"})
