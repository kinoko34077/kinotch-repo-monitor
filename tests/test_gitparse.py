import unittest
from repo_monitor.git_inspector import parse_porcelain_z


class GitParseTests(unittest.TestCase):
    def test_parses_modified_and_untracked_paths(self):
        raw = ' M src/main.py\0?? notes.txt\0'
        self.assertEqual(parse_porcelain_z(raw), ['src/main.py', 'notes.txt'])

    def test_rename_uses_destination_path(self):
        raw = 'R  new.txt\0old.txt\0'
        self.assertEqual(parse_porcelain_z(raw), ['new.txt'])


if __name__ == '__main__':
    unittest.main()

class GitInspectorErrorTests(unittest.TestCase):
    def test_missing_repository_returns_error_snapshot(self):
        from repo_monitor.git_inspector import inspect_repository
        snap = inspect_repository('/definitely/not/a/repository')
        self.assertTrue(snap.error)
