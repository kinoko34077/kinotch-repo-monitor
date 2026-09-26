import tempfile
import unittest
from pathlib import Path

from repo_monitor.config import AppConfig, ConfigStore, RepoEntry
from repo_monitor.devflow_state import DevflowRepoState, DevflowSnapshot
from repo_monitor.git_inspector import RepoSnapshot
from repo_monitor.registry import repo_identity
from repo_monitor.scan_engine import LocalRepoSnapshot, LocalSnapshot
from repo_monitor.web_app import RepoMonitorService


class _FakeDevflowProvider:
    def snapshot(self):
        return DevflowSnapshot(
            repositories={
                "example-repo": DevflowRepoState(
                    repository="example-repo",
                    work_status="IMPLEMENTING",
                    repository_state="ACTIVE",
                    active_work="example-repo#12 — implement",
                    next_action="VERIFY — run CI",
                    issue_number=59,
                    issue_url="https://github.com/kinoko34077/devflow/issues/59",
                    updated_at="2026-09-26T03:00:00Z",
                )
            },
            fetched_at=1000.0,
        )


class _FakeScanEngine:
    def __init__(self, observations):
        self._snapshot = LocalSnapshot(
            generation=1,
            repositories=tuple(
                LocalRepoSnapshot(repo_identity(item.path), item)
                for item in observations
            ),
            completed_at=1000.0,
            duration_ms=10,
        )

    def snapshot(self):
        return self._snapshot

    def request_scan(self):
        return None


class WebAppDevflowTests(unittest.TestCase):
    def test_state_projects_matching_devflow_control_state_separately_from_git_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            managed = root / "example-repo"
            unmanaged = root / "local-only"
            managed.mkdir()
            unmanaged.mkdir()
            store = ConfigStore(root / "config.json")
            store.save(
                AppConfig(
                    repositories=[
                        RepoEntry("example-repo", str(managed)),
                        RepoEntry("local-only", str(unmanaged)),
                    ],
                    scan_roots=[str(root)],
                )
            )

            service = RepoMonitorService(
                store=store,
                scan_engine=_FakeScanEngine(
                    [
                        RepoSnapshot(path=managed, dirty=False),
                        RepoSnapshot(path=unmanaged, dirty=False),
                    ]
                ),
                devflow_provider=_FakeDevflowProvider(),
                clock=lambda: 1000.0,
            )

            state = service.state()
            by_name = {repo["name"]: repo for repo in state["repositories"]}

            self.assertEqual(by_name["example-repo"]["status"], "CLEAN")
            self.assertEqual(by_name["example-repo"]["devflow"]["work_status"], "IMPLEMENTING")
            self.assertEqual(by_name["example-repo"]["devflow"]["repository_state"], "ACTIVE")
            self.assertEqual(by_name["example-repo"]["devflow"]["next_action"], "VERIFY — run CI")
            self.assertIsNone(by_name["local-only"]["devflow"])
            self.assertEqual(state["devflow"]["fetched_at"], 1000.0)
            self.assertFalse(state["devflow"]["stale"])
            self.assertIsNone(state["devflow"]["error"])


if __name__ == "__main__":
    unittest.main()
