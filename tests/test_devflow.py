import unittest
from repo_monitor.devflow import DEFAULT_MANAGED_REPOSITORIES


class DevflowTests(unittest.TestCase):
    def test_current_managed_repo_snapshot_has_30_and_excludes_backups(self):
        self.assertEqual(len(DEFAULT_MANAGED_REPOSITORIES), 30)
        self.assertNotIn('pc-files', DEFAULT_MANAGED_REPOSITORIES)
        self.assertNotIn('pc-files2', DEFAULT_MANAGED_REPOSITORIES)
        self.assertIn('devflow-test', DEFAULT_MANAGED_REPOSITORIES)
        self.assertIn('kinotch-repository-base', DEFAULT_MANAGED_REPOSITORIES)


if __name__ == '__main__':
    unittest.main()
