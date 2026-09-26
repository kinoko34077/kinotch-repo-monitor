import http.client
import json
import threading
import unittest
from unittest.mock import patch

from repo_monitor import web_server
from repo_monitor.web_server import create_server


class _Service:
    def __init__(self):
        self.scan_requests = 0

    def state(self):
        return {"refresh_ms": 2000, "scan": {"generation": 1}, "repositories": []}

    def request_scan(self):
        self.scan_requests += 1


class WebServerLifecycleTests(unittest.TestCase):
    def test_refresh_endpoint_requests_scan_and_returns_promptly(self):
        service = _Service()
        server = create_server(port=0, service=service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request(
                "POST",
                "/api/refresh",
                body=b"{}",
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            data = json.loads(response.read())
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(data, {"scan_requested": True})
            self.assertEqual(service.scan_requests, 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_serve_binds_before_rediscovery_and_owns_scan_lifecycle(self):
        events = []

        class Service:
            def rediscover(self):
                events.append("rediscover")
                return self.state()

            def state(self):
                return {"repositories": []}

            def start_scanning(self):
                events.append("start")

            def stop_scanning(self, timeout=2.0):
                events.append(("stop", timeout))

        class Server:
            server_address = ("127.0.0.1", 17341)

            def serve_forever(self, poll_interval=0.25):
                events.append("serve")

            def server_close(self):
                events.append("close")

        service = Service()

        def bind(host, port, app):
            events.append("bind")
            self.assertIs(app, service)
            return Server()

        with patch("repo_monitor.web_server.create_server", side_effect=bind):
            result = web_server.serve(
                host="127.0.0.1",
                port=17341,
                open_browser=False,
                service=service,
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            ["bind", "rediscover", "start", "serve", ("stop", 2.0), "close"],
        )


if __name__ == "__main__":
    unittest.main()
