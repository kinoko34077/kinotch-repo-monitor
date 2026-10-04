import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_monitor.config import AppConfig, RepoEntry
from repo_monitor.registry import merge_discovered, repo_identity


class RegistryTests(unittest.TestCase):
    def test_repo_identity_caches_filesystem_resolution_for_repeated_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()

            first = repo_identity(repo)
            with mock.patch("pathlib.Path.resolve", side_effect=AssertionError("repeated filesystem resolve used")):
                second = repo_identity(repo)

            self.assertEqual(second, first)

    def test_discovery_does_not_relocate_missing_same_name_repo_without_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old" / "a"
            new = root / "new" / "a"
            new.mkdir(parents=True)
            cfg = AppConfig(
                repositories=[
                    RepoEntry(
                        "a",
                        str(old),
                        "https://chatgpt.com/c/a",
                        monitored=False,
                    )
                ]
            )

            merged = merge_discovered(cfg, [new])

            self.assertEqual(len(merged.repositories), 2)
            old_entry = next(repo for repo in merged.repositories if Path(repo.path) == old)
            new_entry = next(repo for repo in merged.repositories if Path(repo.path) == new.resolve())
            self.assertEqual(old_entry.chat_url, "https://chatgpt.com/c/a")
            self.assertFalse(old_entry.monitored)
            self.assertEqual(new_entry.chat_url, "")
            self.assertTrue(new_entry.monitored)

    def test_discovery_keeps_existing_hidden_repository_hidden_and_preserves_chat_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            cfg = AppConfig(
                repositories=[
                    RepoEntry(
                        "repo",
                        str(repo),
                        "https://chatgpt.com/c/repo",
                        monitored=False,
                    )
                ]
            )

            merged = merge_discovered(cfg, [repo])

            self.assertEqual(len(merged.repositories), 1)
            self.assertFalse(merged.repositories[0].monitored)
            self.assertEqual(merged.repositories[0].chat_url, "https://chatgpt.com/c/repo")

    def test_same_name_repositories_at_different_paths_are_kept_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one" / "same"
            second = root / "two" / "same"
            first.mkdir(parents=True)
            second.mkdir(parents=True)

            merged = merge_discovered(AppConfig(), [first, second])

            self.assertEqual(len(merged.repositories), 2)
            identities = {repo_identity(repo.path) for repo in merged.repositories}
            self.assertEqual(len(identities), 2)
            self.assertEqual({repo.name for repo in merged.repositories}, {"same"})


if __name__ == "__main__":
    unittest.main()
