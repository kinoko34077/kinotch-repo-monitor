import unittest
from repo_monitor.status import classify_status, DisplayStatus


class StatusClassificationTests(unittest.TestCase):
    def test_recent_dirty_change_is_active(self):
        self.assertEqual(
            classify_status(dirty=True, age_seconds=15, ahead=0, git_error=False),
            DisplayStatus.ACTIVE,
        )

    def test_dirty_change_becomes_idle_then_stale(self):
        self.assertEqual(classify_status(True, 120, 0, False), DisplayStatus.IDLE)
        self.assertEqual(classify_status(True, 900, 0, False), DisplayStatus.STALE)

    def test_clean_ahead_of_upstream_is_committed(self):
        self.assertEqual(classify_status(False, None, 2, False), DisplayStatus.COMMITTED)

    def test_clean_synced_repo_is_clean(self):
        self.assertEqual(classify_status(False, None, 0, False), DisplayStatus.CLEAN)

    def test_git_error_wins(self):
        self.assertEqual(classify_status(True, 1, 0, True), DisplayStatus.ERROR)


if __name__ == '__main__':
    unittest.main()
