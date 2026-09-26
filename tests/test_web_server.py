import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote

from repo_monitor import web_server
from repo_monitor.web_server import create_server


class FakeService:
    def __init__(self):
        self.repo_key = r"c:\work\repo name"
        self.chat_url = ""
        self.removed = False
        self.opened = False
        self.rediscovered = False
        self.added_path = ""

    def state(self):
        return {"refresh_ms": 2000, "repositories": [{"key": self.repo_key, "name": "repo name", "status": "CLEAN"}]}

    def rediscover(self):
        self.rediscovered = True
        return self.state()

    def add_repository(self, path):
        if path == "bad":
            raise ValueError("Git repository (.git) not found")
        self.added_path = path
        return {"key": path, "name": "added", "path": path, "chat_url": ""}

    def set_chat_url(self, repo_key, chat_url):
        if repo_key != self.repo_key:
            raise KeyError(repo_key)
        self.chat_url = chat_url
        return {"key": repo_key, "chat_url": chat_url, "has_chat": bool(chat_url)}

    def remove_repository(self, repo_key):
        if repo_key != self.repo_key:
            raise KeyError(repo_key)
        self.removed = True
        return {"key": repo_key, "removed": True}

    def open_folder(self, repo_key):
        if repo_key != self.repo_key:
            raise KeyError(repo_key)
        self.opened = True


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.server = create_server(port=0, service=self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        payload = None if body is None else (body if isinstance(body, bytes) else body.encode("utf-8"))
        conn.request(method, path, body=payload, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        conn.close()
        return result

    def test_state_endpoint_returns_json(self):
        status, headers, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["repositories"][0]["status"], "CLEAN")

    def test_send_bytes_quietly_ends_when_client_disconnects(self):
        handler_type = web_server._handler_for(self.service, Path("."))
        disconnects = (
            ConnectionAbortedError(10053, "connection aborted"),
            ConnectionResetError(10054, "connection reset"),
            BrokenPipeError(32, "broken pipe"),
        )
        for disconnect in disconnects:
            with self.subTest(disconnect=type(disconnect).__name__):
                handler = object.__new__(handler_type)
                handler.send_response = Mock()
                handler.send_header = Mock()
                handler.end_headers = Mock()
                handler.wfile = Mock()
                handler.wfile.write.side_effect = disconnect
                handler._send_bytes(200, b"{}", "application/json; charset=utf-8")
                handler.wfile.write.assert_called_once_with(b"{}")

    def test_chat_url_route_round_trips_encoded_windows_repo_key(self):
        encoded = quote(self.service.repo_key, safe="")
        status, _, body = self.request(
            "POST",
            f"/api/repos/{encoded}/chat-url",
            json.dumps({"chat_url": "https://chatgpt.com/c/x"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["chat_url"], "https://chatgpt.com/c/x")
        self.assertEqual(self.service.chat_url, "https://chatgpt.com/c/x")

    def test_manual_add_validates_path_payload(self):
        status, _, body = self.request(
            "POST",
            "/api/repos/add",
            json.dumps({"path": r"C:\work\manual"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.service.added_path, r"C:\work\manual")
        self.assertEqual(json.loads(body)["name"], "added")

        status, _, body = self.request(
            "POST",
            "/api/repos/add",
            json.dumps({"path": "bad"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertIn("Git repository", json.loads(body)["error"])

    def test_malformed_json_is_400_and_unknown_repo_is_404(self):
        encoded = quote(self.service.repo_key, safe="")
        status, _, _ = self.request("POST", f"/api/repos/{encoded}/chat-url", b"{bad", {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

        missing = quote("missing", safe="")
        status, _, body = self.request("POST", f"/api/repos/{missing}/remove", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "repository not found")

    def test_actions_rediscover_remove_and_open_folder(self):
        encoded = quote(self.service.repo_key, safe="")
        self.assertEqual(self.request("POST", "/api/rediscover", b"{}", {"Content-Type": "application/json"})[0], 200)
        self.assertTrue(self.service.rediscovered)
        self.assertEqual(self.request("POST", f"/api/repos/{encoded}/open-folder", b"{}", {"Content-Type": "application/json"})[0], 200)
        self.assertTrue(self.service.opened)
        self.assertEqual(self.request("POST", f"/api/repos/{encoded}/remove", b"{}", {"Content-Type": "application/json"})[0], 200)
        self.assertTrue(self.service.removed)

    def test_nonlocal_host_header_is_rejected_for_get(self):
        status, _, body = self.request("GET", "/api/state", headers={"Host": "attacker.example"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "local request required")

    def test_cross_origin_post_is_rejected_before_action(self):
        status, _, body = self.request(
            "POST",
            "/api/rediscover",
            b"{}",
            {"Content-Type": "application/json", "Origin": "https://attacker.example"},
        )
        self.assertEqual(status, 403)
        self.assertFalse(self.service.rediscovered)
        self.assertEqual(json.loads(body)["error"], "local origin required")

    def test_non_json_post_is_rejected_before_action(self):
        status, _, body = self.request(
            "POST",
            "/api/rediscover",
            b"{}",
            {"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 415)
        self.assertFalse(self.service.rediscovered)
        self.assertEqual(json.loads(body)["error"], "application/json required")

    def test_unknown_paths_and_static_path_traversal_are_not_served(self):
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)
        self.assertEqual(self.request("GET", "/../config.py")[0], 404)
        self.assertEqual(self.request("GET", "/web/../config.py")[0], 404)

    def test_non_loopback_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            create_server(host="0.0.0.0", port=0, service=self.service)


if __name__ == "__main__":
    unittest.main()
