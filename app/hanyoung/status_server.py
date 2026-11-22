"""Chrome 확장이 '앱이 켜져 있는지' 알 수 있게 이 컴퓨터 안에서만 상태를 알려 주는 작은 HTTP 서버

- 주소: http://127.0.0.1:47321/status → {"app": "HanYoungFix", "enabled": true}
- 127.0.0.1에만 열리므로 다른 컴퓨터에서는 접근할 수 없음
- CORS 헤더를 보내지 않으므로 웹사이트 스크립트는 내용을 읽을 수 없음 (확장은 host_permissions로 읽음)
- 앱이 켜져 있고 교정이 켜져 있으면 확장은 스스로 쉬어 같은 글자를 두 번 고치지 않음
"""
from __future__ import annotations

import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 47321


def start(get_enabled, port: int = PORT):
    """백그라운드에서 서버를 띄움. 포트가 이미 쓰이면 None (앱은 그대로 동작)"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.split('?')[0] != '/status':
                self.send_error(404)
                return
            body = json.dumps({'app': 'HanYoungFix', 'enabled': bool(get_enabled())}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 접속 기록을 남기지 않음
            pass

    class Server(ThreadingHTTPServer):
        allow_reuse_address = False  # Windows에서 같은 포트를 두 번 여는 것을 막음

        def server_bind(self):
            # HTTPServer.server_bind는 socket.getfqdn()으로 컴퓨터 이름을 찾는데, Mac에서는 이게
            # 수십 초 걸려 앱 시작(키보드 감시)이 늦어졌음 (CI 실측). 이름 찾기 없이 바로 묶음
            socketserver.TCPServer.server_bind(self)
            self.server_name, self.server_port = self.server_address[:2]

    try:
        server = Server(('127.0.0.1', port), Handler)
    except OSError as e:
        print('status server not started, errno', getattr(e, 'errno', None))  # 콘솔 인코딩과 상관없이 안전하게 (ASCII만)
        return None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name='hanyoung-status').start()
    return server
