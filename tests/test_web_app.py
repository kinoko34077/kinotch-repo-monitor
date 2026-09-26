import tempfile
import unittest
from pathlib import Path

from repo_monitor.config import AppConfig, ConfigStore, RepoEntry
from repo_monitor.git_inspector import RepoSnapshot
from repo_monitor.registry import repo_identity
from repo_monitor.web_app import RepoMonitorService


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

            def inspector(paths, *, max_workers=4):
                return [
                    RepoSnapshot(path=Path(paths[0]), branch="main", head="11111111", dirty=True, changed_count=1, latest_activity_ts=990.0),
                    RepoSnapshot(path=Path(paths[1]), branch="dev", head="22222222", dirty=False, ahead=1, upstream="origin/dev"),
                ]

            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                inspector=inspector,
                clock=lambda: 1000.0,
            )
            state = service.state()

            self.assertEqual(len(state["repositories"]), 2)
            self.assertEqual({item["key"] for item in state["repositories"]}, {repo_identity(first), repo_identity(second)})
            self.assertEqual([item["status"] for item in state["repositories"]], ["ACTIVE", "COMMITTED"])
            self.assertEqual(state["refresh_ms"], 2000)

    def test_state_projects_remote_web_url_from_git_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            store = self.make_store(root, [RepoEntry("repo", str(repo))])

            def inspector(paths, *, max_workers=4):
                snap = RepoSnapshot(path=Path(paths[0]))
                snap.remote_web_url = "https://github.com/kinoko34077/repo"
                return [snap]

            service = RepoMonitorService(store=store, discoverer=lambda _roots: [], inspector=inspector)
            item = service.state()["repositories"][0]
            self.assertEqual(item.get("remote_web_url"), "https://github.com/kinoko34077/repo")

    def test_chat_url_is_persisted_and_unknown_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            service = RepoMonitorService(store=store, discoverer=lambda _roots: [], inspector=lambda paths, *, max_workers=4: [RepoSnapshot(path=Path(p)) for p in paths])

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
            store = self.make_store(root, [RepoEntry("first", str(first), "https://chatgpt.com/c/first")])
            discovered = [first, second]
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: list(discovered),
                inspector=lambda paths, *, max_workers=4: [RepoSnapshot(path=Path(p)) for p in paths],
            )

            service.rediscover()
            self.assertEqual({repo.name for repo in store.load().repositories}, {"first", "second"})
            first_entry = next(repo for repo in store.load().repositories if repo.name == "first")
            self.assertEqual(first_entry.chat_url, "https://chatgpt.com/c/first")

            service.remove_repository(repo_identity(second))
            self.assertEqual([repo.name for repo in store.load().repositories], ["first"])

    def test_manual_repository_add_validates_git_directory_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = self.make_store(root, [])
            service = RepoMonitorService(store=store, discoverer=lambda _roots: [], inspector=lambda paths, *, max_workers=4: [RepoSnapshot(path=Path(p)) for p in paths])
            repo = root / "outside" / "manual"
            (repo / ".git").mkdir(parents=True)

            added = service.add_repository(str(repo))

            self.assertEqual(added["name"], "manual")
            self.assertEqual(added["key"], repo_identity(repo))
            persisted = store.load()
            self.assertEqual(len(persisted.repositories), 1)
            self.assertEqual(repo_identity(persisted.repositories[0].path), repo_identity(repo))

            with self.assertRaises(ValueError):
                service.add_repository(str(root / "not-a-repo"))

    def test_open_folder_uses_injected_opener_and_rejects_unknown_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            opened: list[str] = []
            store = self.make_store(root, [RepoEntry("repo", str(repo))])
            service = RepoMonitorService(
                store=store,
                discoverer=lambda _roots: [],
                inspector=lambda paths, *, max_workers=4: [RepoSnapshot(path=Path(p)) for p in paths],
                folder_opener=opened.append,
            )

            service.open_folder(repo_identity(repo))
            self.assertEqual(opened, [str(repo)])
            with self.assertRaises(KeyError):
                service.open_folder("missing")


if __name__ == "__main__":
    unittest.main()
