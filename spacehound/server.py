"""Tiny HTTP bridge so the UI also runs in a normal browser (``--browser``).

Static files are served from the ui folder; API calls are POST /api/<method>
with a JSON body ``{"args": [...]}``. Every API call must carry the random
per-session token, and the Host header must be the loopback address, so other
web pages cannot drive the API.
"""

import json
import mimetypes
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .util import resource_path


class _Handler(BaseHTTPRequestHandler):
    server_version = "SpaceHound"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain")
        path = urlparse(self.path).path
        if path in ("", "/"):
            path = "/index.html"
        root = self.server.ui_root
        full = os.path.normpath(os.path.join(root, path.lstrip("/")))
        if not full.startswith(root) or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, json.dumps({"ok": False, "error": "forbidden"}))
        if not secrets.compare_digest(self.headers.get("X-SpaceHound-Token", ""), self.server.token):
            return self._send(403, json.dumps({"ok": False, "error": "bad token"}))
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._send(404, json.dumps({"ok": False, "error": "not found"}))
        name = path[5:]
        fn = getattr(self.server.api, name, None)
        if name.startswith("_") or not callable(fn):
            return self._send(404, json.dumps({"ok": False, "error": f"unknown method {name}"}))
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = fn(*payload.get("args", []))
            body = json.dumps({"ok": True, "result": result}, default=str)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": f"{exc}"})
        self._send(200, body)


def serve(api, port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    server.api = api
    server.token = secrets.token_urlsafe(24)
    server.ui_root = os.path.normpath(resource_path("ui"))
    thread = threading.Thread(target=server.serve_forever, name="http-bridge", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html?token={server.token}"
    return server, url
