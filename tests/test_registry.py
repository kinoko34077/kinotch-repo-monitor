import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_monitor.config import AppConfig, RepoEntry
from repo_monitor.registry import merge_discovered, repo_identity


class RegistryTests(unittest.TestCase):
    def test_repo_identity_does_not_resolve_through_filesystem(self):
        relative = Path("nested") / ".." / "repo"
        expected = os.path.normcase(os.path.abspath(os.path.expanduser(str(relative))))

        with mock.patch("pathlib.Path.resolve", side_effect=AssertionError("filesystem resolve used")):
            actual = repo_identity(relative)

        self.assertEqual(actual, expected)

    def test_discovery_relocates_missing_same_name_repo_without_overwriting_chat_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old" / "a"
            new = root / "new" / "a"
            new.mkdir(parents=True)
            cfg = AppConfig(repositories=[RepoEntry("a", str(old), "https://chatgpt.com/c/a")])

            merged = merge_discovered(cfg, [new])

            self.assertEqual(len(merged.repositories), 1)
            self.assertEqual(merged.repositories[0].chat_url, "https://chatgpt.com/c/a")
            self.assertEqual(Path(merged.repositories[0].path), new.resolve())

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
