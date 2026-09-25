import unittest
from repo_monitor.git_inspector import parse_status_v2


class GitStatusV2Tests(unittest.TestCase):
    def test_parses_branch_sync_and_changed_paths(self):
        raw = (
            '# branch.oid abcdef1234567890\0'
            '# branch.head main\0'
            '# branch.upstream origin/main\0'
            '# branch.ab +2 -1\0'
            '1 .M N... 100644 100644 100644 aaa bbb src/main.py\0'
            '? notes.txt\0'
        )
        data = parse_status_v2(raw)
        self.assertEqual(data['head'], 'abcdef12')
        self.assertEqual(data['branch'], 'main')
        self.assertEqual(data['upstream'], 'origin/main')
        self.assertEqual(data['ahead'], 2)
        self.assertEqual(data['behind'], 1)
        self.assertEqual(data['paths'], ['src/main.py', 'notes.txt'])

    def test_rename_keeps_destination_and_skips_source(self):
        raw = '2 R. N... 100644 100644 100644 aaa bbb R100 new.txt\0old.txt\0'
        self.assertEqual(parse_status_v2(raw)['paths'], ['new.txt'])


if __name__ == '__main__':
    unittest.main()
