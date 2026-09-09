import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _Stub:
    def __init__(self):
        self.requests = []
        self.get_requests = []
        self.status_queue = []
        self.default_status = 200
        self.redirect_to = None
        self.redirect_status = 302

    def next_status(self):
        if self.status_queue:
            return self.status_queue.pop(0)
        return self.default_status


@pytest.fixture
def webhook():
    """A local webhook server. `webhook.url` is postable; `webhook.requests` records hits."""
    stub = _Stub()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8")
            stub.requests.append({"path": self.path, "body": json.loads(raw) if raw else None})
            if stub.redirect_to:
                self.send_response(stub.redirect_status)
                self.send_header("Location", stub.redirect_to)
                self.end_headers()
                return
            status = stub.next_status()
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            # Records whether a redirect target was actually hit (it must not be).
            stub.get_requests.append({"path": self.path})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stub.url = "http://127.0.0.1:%d/webhook?key=SECRET123" % server.server_address[1]
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()
