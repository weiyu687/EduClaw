"""Loopback-only dashboard. Static UI is public; all task data requires bearer auth."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlsplit

from core.gui.service import DashboardService


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, directory, static_directory, port=0):
        self.service = DashboardService(directory)
        self.static_directory = Path(static_directory).resolve()
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Never log request URLs, bearer credentials or private task data.

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        data = json.dumps(body, ensure_ascii=False).encode() if not isinstance(body, bytes) else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def boundary(self, api=False, mutation=False):
        server = self.server
        if self.headers.get_all('Host') != [f'127.0.0.1:{server.server_port}']:
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin != server.origin:
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        if mutation and origin != server.origin:
            return False
        if api:
            headers = self.headers.get_all('Authorization') or []
            if len(headers) != 1 or not hmac.compare_digest(headers[0], 'Bearer ' + server.token):
                return False
        return True

    def do_GET(self):
        path = urlsplit(self.path)
        api = path.path.startswith('/api/')
        if not self.boundary(api=api):
            return self.reply(403, {'error':'连接凭据或来源无效，请用本次启动地址重新连接。'})
        if not api:
            relative = 'index.html' if path.path == '/' else path.path.lstrip('/')
            if relative != 'index.html' and not relative.startswith('assets/'):
                return self.reply(404, {'error':'页面不存在。'})
            target = (self.server.static_directory / relative).resolve()
            if not target.is_relative_to(self.server.static_directory) or not target.is_file():
                return self.reply(404, {'error':'请先构建 web 界面。'})
            types = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}
            if target.suffix not in types:
                return self.reply(404, {'error':'页面不存在。'})
            return self.reply(200, target.read_bytes(), types[target.suffix])
        try:
            query = parse_qs(path.query, strict_parsing=True)
            if any(len(v) != 1 or len(v[0]) > 128 for v in query.values()):
                raise ValueError('请求参数无效。')
            params = {k:v[0] for k,v in query.items()}
            service = self.server.service
            if path.path == '/api/sessions' and not params:
                result = service.sessions()
            elif path.path == '/api/tasks' and set(params) == {'session'}:
                result = service.tasks(params['session'])
            elif path.path == '/api/task' and set(params) == {'session','number'}:
                result = service.detail(params['session'], int(params['number']))
            elif path.path == '/api/events' and set(params) == {'session','number','after'}:
                result = service.events(params['session'], int(params['number']), int(params['after']))
            else:
                return self.reply(404, {'error':'接口不存在。'})
            self.reply(200, result)
        except (ValueError, LookupError, PermissionError) as exc:
            self.reply(409, {'error':str(exc)})
        except Exception:
            self.reply(500, {'error':'无法读取任务数据，请检查数据目录和 CLI 诊断。'})

    def do_POST(self):
        if not self.boundary(api=True, mutation=True):
            return self.reply(403, {'error':'操作来源或连接凭据无效。'})
        try:
            lengths = self.headers.get_all('Content-Length') or []
            if (self.headers.get('Transfer-Encoding') or len(lengths) != 1 or
                    self.headers.get('Content-Type') != 'application/json'):
                raise ValueError('仅接受定长 JSON 请求。')
            length = int(lengths[0])
            if not 0 < length <= 4096:
                raise ValueError('请求长度无效。')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('请求必须为对象。')
            service = self.server.service
            if self.path == '/api/preview' and set(body) == {'session','number','action'}:
                result = service.preview(body['session'], body['number'], body['action'])
            elif self.path == '/api/confirm' and set(body) == {'ticket','confirmation'}:
                result = service.confirm(body['ticket'], body['confirmation'])
            else:
                return self.reply(404, {'error':'接口不存在。'})
            self.reply(200, result)
        except (ValueError, LookupError, PermissionError, TypeError) as exc:
            self.reply(409, {'error':str(exc)})
        except Exception:
            self.reply(500, {'error':'操作未能确认完成。请刷新核查状态，不要重复提交。'})

    def do_OPTIONS(self):
        self.reply(403, {'error':'不允许跨域访问。'})


def main():
    parser = argparse.ArgumentParser(description='EduClaw 本地任务界面')
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    static = Path(__file__).resolve().parents[2] / 'web' / 'dist'
    if not (static / 'index.html').exists():
        parser.error('请先在 web 目录执行 npm ci 和 npm run build')
    server = DashboardServer(args.data_dir, static, args.port)
    print(f'打开本次启动地址（仅本机，关闭服务即失效）：{server.origin}/#token={server.token}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
