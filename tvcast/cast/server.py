"""HTTP server that streams live MPEG-TS to a DLNA renderer.

What the real TV (Android stagefright) taught us: it sends HEAD first, then a ranged
GET. It is happy with HTTP/1.0 framing, no Content-Length, no Range support, as long
as the DLNA transfer headers are present.
"""
import http.server
import socketserver
import threading

DLNA_HEADERS = {
    "transferMode.dlna.org": "Streaming",
    "contentFeatures.dlna.org": ("DLNA.ORG_OP=00;DLNA.ORG_CI=0;"
                                 "DLNA.ORG_FLAGS=01700000000000000000000000000000"),
    "Accept-Ranges": "none",
}
CHUNK = 188 * 64


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):  # keep stderr for our own log
        pass

    def _record(self):
        rec = {"method": self.command, "path": self.path, "client": self.client_address[0],
               "headers": dict(self.headers.items())}
        self.server.requests.append(rec)
        if self.server.log:
            self.server.log(f"{self.client_address[0]} {self.command} {self.path} "
                            f"UA={self.headers.get('User-Agent', '-')}")

    def _send_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mpeg")
        for k, v in DLNA_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()

    def _wanted(self):
        return self.path.split("?")[0] == self.server.path

    def do_HEAD(self):
        self._record()
        if not self._wanted():
            self.send_error(404)
            return
        self._send_headers()

    def do_GET(self):
        self._record()
        if not self._wanted():
            self.send_error(404)
            return
        self._send_headers()
        capture = self.server.capture_factory()
        sent = 0
        try:
            while True:
                chunk = capture.read(CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            capture.stop()
            if self.server.log:
                self.server.log(f"{self.client_address[0]} disconnected after {sent} bytes")


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class StreamServer:
    path = "/screen.ts"

    def __init__(self, capture_factory, host="0.0.0.0", port=0, log=None):
        self.capture_factory = capture_factory
        self.host, self.port, self.log = host, port, log
        self.requests = []
        self._srv = None
        self._thread = None

    def start(self):
        self._srv = _Server((self.host, self.port), _Handler)
        self._srv.capture_factory = self.capture_factory
        self._srv.requests = self.requests
        self._srv.log = self.log
        self._srv.path = self.path
        self.port = self._srv.server_address[1]
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None
