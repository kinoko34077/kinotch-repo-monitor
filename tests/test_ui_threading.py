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
            "repo_monitor.ui.inspect_repositories", return_value=["snapshot"]
        ) as inspect_many:
            app.refresh()

        self.assertEqual(app.root.after_calls, [])
        inspect_many.assert_called_once()
        self.assertEqual(app._result_queue.get_nowait()[0][1], "snapshot")

    def test_repo_key_uses_path_so_equal_names_do_not_collide(self):
        first = RepoEntry("same", "C:/one/same")
        second = RepoEntry("same", "C:/two/same")
        self.assertNotEqual(RepoMonitorApp._repo_key(first), RepoMonitorApp._repo_key(second))

    def test_repository_order_is_local_name_order_not_static_devflow_snapshot(self):
        app = object.__new__(RepoMonitorApp)
        app.config = AppConfig(
            repositories=[
                RepoEntry("weather-widget", "C:/repos/weather-widget"),
                RepoEntry("alpha-local", "C:/repos/alpha-local"),
            ]
        )
        self.assertEqual(
            [repo.name for repo in app._ordered_repos()],
            ["alpha-local", "weather-widget"],
        )


if __name__ == "__main__":
    unittest.main()
