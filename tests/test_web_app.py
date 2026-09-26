import tempfile
import unittest
from pathlib import Path

from repo_monitor.config import AppConfig, ConfigStore, RepoEntry
from repo_monitor.git_inspector import RepoSnapshot
from repo_monitor.registry import repo_identity
from repo_monitor.scan_engine import LocalRepoSnapshot, LocalSnapshot
from repo_monitor.web_app import RepoMonitorService


class _FakeScanEngine:
    def __init__(self, snapshot: LocalSnapshot | None = None):
        self.current = snapshot or LocalSnapshot()
        self.requests = 0
        self.started = 0
        self.stopped = 0

    def snapshot(self):
        return self.current

    def request_scan(self):
        self.requests += 1

    def start(self):
        self.started += 1

    def stop(self, timeout=2.0):
        self.stopped += 1


def _snapshot(*observations: RepoSnapshot, generation: int = 1, **metadata) -> LocalSnapshot:
    return LocalSnapshot(
        generation=generation,
        repositories=tuple(
            LocalRepoSnapshot(repo_identity(observation.path), observation)
            for observation in observations
        ),
        completed_at=metadata.pop("completed_at", 1000.0),
        duration_ms=metadata.pop("duration_ms", 10),
        **metadata,
    )


class WebAppServiceTests(unittest.TestCase):
    def make_store(self, root: Path, repos: list[RepoEntry]) -> ConfigStore:
        store = ConfigStore(root / "config.json")
        store.save(AppConfig(repositories=repos, scan_roots=[str(root)]))
        return store

    def test_state_keeps_equal_repo_names_distinct_and_classifies_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one" / "same"
            second = root / "two" / "same"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            store = self.make_store(
                root,
                [RepoEntry("same", str(first)), RepoEntry("same", str(second))],
            )
            engine = _FakeScanEngine(
                _snapshot(
                    RepoSnapshot(path=first, branch="main", head="11111111", dirty=True, changed_count=1, latest_activity_ts=990.0),
                    RepoSnapshot(path=second, branch="dev", head="22222222", dirty=False, ahead=1, upstream="origin/dev"),
                )
            )
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                scan_engine=engine,
                inspector=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("state must not inspect Git")),
                clock=lambda: 1000.0,
            )
            state = service.state()

            self.assertEqual(len(state["repositories"]), 2)
            self.assertEqual({item["key"] for item in state["repositories"]}, {repo_identity(first), repo_identity(second)})
            self.assertEqual([item["status"] for item in state["repositories"]], ["ACTIVE", "COMMITTED"])
            self.assertEqual(state["refresh_ms"], 2000)
            self.assertEqual(state["scan"]["generation"], 1)

    def test_state_projects_remote_web_url_from_cached_git_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            snap = RepoSnapshot(path=repo)
            snap.remote_web_url = "https://github.com/kinoko34077/repo"
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                scan_engine=_FakeScanEngine(_snapshot(snap)),
            )
            item = service.state()["repositories"][0]
            self.assertEqual(item.get("remote_web_url"), "https://github.com/kinoko34077/repo")

    def test_state_keeps_monitored_registry_entry_pending_until_it_has_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                scan_engine=_FakeScanEngine(LocalSnapshot(in_progress=True)),
            )

            state = service.state()

            self.assertEqual(len(state["repositories"]), 1)
            self.assertEqual(state["repositories"][0]["status"], "PENDING")
            self.assertEqual(state["repositories"][0]["branch"], "?")
            self.assertTrue(state["scan"]["in_progress"])

    def test_state_reclassifies_cached_dirty_observation_against_current_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            engine = _FakeScanEngine(
                _snapshot(RepoSnapshot(path=repo, dirty=True, changed_count=1, latest_activity_ts=990.0))
            )
            now = [1000.0]
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                scan_engine=engine,
                clock=lambda: now[0],
            )

            self.assertEqual(service.state()["repositories"][0]["status"], "ACTIVE")
            now[0] = 1700.0
            self.assertEqual(service.state()["repositories"][0]["status"], "STALE")

    def test_chat_url_is_persisted_and_unknown_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            service = RepoMonitorService(store=store, discoverer=lambda _roots: [], scan_engine=_FakeScanEngine())

            service.set_chat_url(repo_identity(repo), "https://chatgpt.com/c/example")

            persisted = store.load()
            self.assertEqual(persisted.repositories[0].chat_url, "https://chatgpt.com/c/example")
            with self.assertRaises(KeyError):
                service.set_chat_url("missing", "https://example.com")

    def test_remove_and_rediscover_update_registry_without_losing_existing_chat_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (second / ".git").mkdir()
            store = self.make_store(root, [RepoEntry("first", str(first), "https://chatgpt.com/c/first")])
            discovered = [first, second]
            engine = _FakeScanEngine()
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: list(discovered),
                scan_engine=engine,
            )

            service.rediscover()
            self.assertEqual({repo.name for repo in store.load().repositories}, {"first", "second"})
            first_entry = next(repo for repo in store.load().repositories if repo.name == "first")
            self.assertEqual(first_entry.chat_url, "https://chatgpt.com/c/first")

            service.set_chat_url(repo_identity(second), "https://chatgpt.com/c/second")
            service.remove_repository(repo_identity(second))
            hidden = next(repo for repo in store.load().repositories if repo.name == "second")
            self.assertFalse(hidden.monitored)
            self.assertEqual(hidden.chat_url, "https://chatgpt.com/c/second")
            self.assertNotIn("second", {item["name"] for item in service.state()["repositories"]})

            service.rediscover()
            still_hidden = next(repo for repo in store.load().repositories if repo.name == "second")
            self.assertFalse(still_hidden.monitored)
            self.assertEqual(still_hidden.chat_url, "https://chatgpt.com/c/second")

            readded = service.add_repository(str(second))
            self.assertEqual(readded["chat_url"], "https://chatgpt.com/c/second")
            restored = next(repo for repo in store.load().repositories if repo.name == "second")
            self.assertTrue(restored.monitored)
            self.assertGreaterEqual(engine.requests, 3)

    def test_manual_repository_add_validates_git_directory_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root, [])
            engine = _FakeScanEngine()
            service = RepoMonitorService(store=store, discoverer=lambda _roots: [], scan_engine=engine)
            repo = root / "outside" / "manual"
            (repo / ".git").mkdir(parents=True)

            added = service.add_repository(str(repo))

            self.assertEqual(added["name"], "manual")
            self.assertEqual(added["key"], repo_identity(repo))
            persisted = store.load()
            self.assertEqual(len(persisted.repositories), 1)
            self.assertEqual(repo_identity(persisted.repositories[0].path), repo_identity(repo))
            self.assertEqual(engine.requests, 1)

            with self.assertRaises(ValueError):
                service.add_repository(str(root / "not-a-repo"))

    def test_open_folder_uses_injected_opener_and_rejects_unknown_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            opened: list[str] = []
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            engine = _FakeScanEngine()
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                scan_engine=engine,
                folder_opener=opened.append,
            )

            service.open_folder(repo_identity(repo))
            self.assertEqual(opened, [str(repo)])
            self.assertEqual(engine.requests, 0)
            with self.assertRaises(KeyError):
                service.open_folder("missing")


if __name__ == "__main__":
    unittest.main()
