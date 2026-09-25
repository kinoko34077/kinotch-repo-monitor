import tempfile
import unittest
from pathlib import Path
from repo_monitor.discovery import discover_repositories


class DiscoveryTests(unittest.TestCase):
    def test_discovers_direct_child_git_repositories_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / 'a'; a.mkdir(); (a / '.git').mkdir()
            b = root / 'b'; b.mkdir(); (b / '.git').mkdir()
            found = discover_repositories([str(root), str(root)])
            self.assertEqual([p.name for p in found], ['a', 'b'])


if __name__ == '__main__':
    unittest.main()
