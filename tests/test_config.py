import tempfile
import unittest
from pathlib import Path
from repo_monitor.config import ConfigStore, AppConfig, RepoEntry


class ConfigTests(unittest.TestCase):
    def test_round_trip_preserves_chat_url_and_repo_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            store = ConfigStore(path)
            config = AppConfig(repositories=[RepoEntry('demo', 'C:/repo', 'https://chatgpt.com/c/demo')])
            store.save(config)
            loaded = store.load()
            self.assertEqual(loaded.repositories[0].name, 'demo')
            self.assertEqual(loaded.repositories[0].chat_url, 'https://chatgpt.com/c/demo')

    def test_missing_config_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp) / 'missing.json')
            config = store.load()
            self.assertEqual(config.columns, 5)
            self.assertTrue(config.scan_roots)


if __name__ == '__main__':
    unittest.main()
