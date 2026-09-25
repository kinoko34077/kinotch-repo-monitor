import unittest
from pathlib import Path
from repo_monitor.config import AppConfig, RepoEntry
from repo_monitor.registry import merge_discovered


class RegistryTests(unittest.TestCase):
    def test_discovery_adds_missing_repo_without_overwriting_chat_url(self):
        cfg = AppConfig(repositories=[RepoEntry('a', 'C:/old/a', 'https://chatgpt.com/c/a')])
        merged = merge_discovered(cfg, [Path('C:/new/a'), Path('C:/new/b')])
        by_name = {r.name: r for r in merged.repositories}
        self.assertEqual(by_name['a'].chat_url, 'https://chatgpt.com/c/a')
        self.assertEqual(by_name['a'].path, 'C:/new/a')
        self.assertIn('b', by_name)


if __name__ == '__main__':
    unittest.main()
