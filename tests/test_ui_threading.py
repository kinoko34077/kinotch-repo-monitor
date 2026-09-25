import queue
import unittest
from unittest.mock import patch

from repo_monitor.config import AppConfig, RepoEntry
from repo_monitor.ui import RepoMonitorApp


class FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, *args):
        self.after_calls.append(args)


class ImmediateThread:
    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class UiThreadingTests(unittest.TestCase):
    def test_refresh_worker_does_not_call_tk(self):
        app = object.__new__(RepoMonitorApp)
        app.root = FakeRoot()
        app.config = AppConfig(repositories=[RepoEntry("demo", "C:/demo")])
        app.refreshing = False
        app._result_queue = queue.Queue()

        with patch("repo_monitor.ui.threading.Thread", ImmediateThread), patch(
            "repo_monitor.ui.inspect_repository", return_value="snapshot"
        ):
            app.refresh()

        self.assertEqual(app.root.after_calls, [])
        self.assertEqual(app._result_queue.get_nowait()[0][1], "snapshot")


if __name__ == "__main__":
    unittest.main()
