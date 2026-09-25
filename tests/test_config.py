import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_monitor.config import ConfigStore, AppConfig, RepoEntry


class ConfigTests(unittest.TestCase):
    def test_round_trip_preserves_chat_url_and_repo_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            store = ConfigStore(path)
            config = AppConfig(repositories=[RepoEntry("demo", "C:/repo", "https://chatgpt.com/c/demo")])
            store.save(config)
            loaded = store.load()
            self.assertEqual(loaded.repositories[0].name, "demo")
            self.assertEqual(loaded.repositories[0].chat_url, "https://chatgpt.com/c/demo")

    def test_missing_config_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp) / "missing.json")
            config = store.load()
            self.assertEqual(config.columns, 5)
            self.assertTrue(config.scan_roots)

    def test_malformed_config_is_quarantined_and_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            store = ConfigStore(path)

            config = store.load()

            self.assertEqual(config.columns, 5)
            self.assertFalse(path.exists())
            self.assertTrue((Path(tmp) / "config.json.corrupt").exists())

    def test_save_uses_atomic_replace_and_leaves_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            store = ConfigStore(path)
            config = AppConfig(repositories=[RepoEntry("demo", "C:/repo")])

            real_replace = os.replace
            with patch("repo_monitor.config.os.replace", wraps=real_replace) as replace:
                store.save(config)

            replace.assert_called_once()
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["repositories"][0]["name"], "demo")
            leftovers = [p for p in Path(tmp).iterdir() if p.name != "config.json"]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
