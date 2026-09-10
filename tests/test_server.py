import http.client
import io
import threading
import unittest

from tvcast.cast.server import StreamServer, DLNA_HEADERS


class FakeCapture:
    def __init__(self, payload):
        self.buf = io.BytesIO(payload)
        self.stopped = threading.Event()

    def read(self, n):
        return self.buf.read(n)

    def stop(self):
        self.stopped.set()


class TestStreamServer(unittest.TestCase):
    def setUp(self):
        self.captures = []

        def factory():
            cap = FakeCapture(b"\x47" * 188 * 10)
            self.captures.append(cap)
            return cap

        self.server = StreamServer(factory, host="127.0.0.1", port=0)
        self.port = self.server.start()

    def tearDown(self):
        self.server.stop()

    def test_head_returns_dlna_headers_without_body(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("HEAD", "/screen.ts")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "video/mpeg")
        for k, v in DLNA_HEADERS.items():
            self.assertEqual(resp.getheader(k), v)
        self.assertIsNone(resp.getheader("Content-Length"))
        self.assertEqual(self.captures, [])
        self.assertEqual(self.server.requests[-1]["method"], "HEAD")
        self.assertEqual(self.server.requests[-1]["client"], "127.0.0.1")

    def test_get_streams_capture_then_stops_it(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/screen.ts", headers={"Range": "bytes=0-"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read()
        self.assertEqual(len(body), 188 * 10)
        self.assertTrue(self.captures[0].stopped.wait(5))
        self.assertEqual(self.server.requests[-1]["headers"].get("Range"), "bytes=0-")

    def test_client_disconnect_stops_capture(self):
        class Endless:
            def __init__(self):
                self.stopped = threading.Event()

            def read(self, n):
                return b"\x47" * n

            def stop(self):
                self.stopped.set()

        cap = Endless()
        server = StreamServer(lambda: cap, host="127.0.0.1", port=0)
        port = server.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/screen.ts")
            resp = conn.getresponse()
            resp.read(1000)
            resp.close()  # the response holds the socket open until it is closed too
            conn.close()
            self.assertTrue(cap.stopped.wait(5))
        finally:
            server.stop()

    def test_unknown_path_is_404(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/nope")
        self.assertEqual(conn.getresponse().status, 404)


if __name__ == "__main__":
    unittest.main()
