"""Scheduled M7 must be one-source, private and separate from Issue fleet."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCHEDULED = ROOT / ".github/workflows/history-archive-pr-body-one-source.yml"
ISSUE_FLEET = ROOT / ".github/workflows/history-archive-fleet-hourly.yml"

class OneSourceScheduleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schedule = SCHEDULED.read_text(encoding="utf-8")
        cls.fleet = ISSUE_FLEET.read_text(encoding="utf-8")

    def test_only_one_private_pr_source_and_two_daily_runs(self):
        s = self.schedule
        self.assertIn('cron: "47 3,15 * * *"', s)
        self.assertIn("workflow_dispatch: {}", s)
        self.assertEqual(s.count("repository: kinoko34077/github-history-archive"), 2)
        self.assertIn("ref: pilot/v02-multipage-pr-body-20261103", s)
        self.assertIn("ref: main", s)
        self.assertNotIn("fleet-repositories.txt", s)

    def test_existing_runtime_and_remote_cursor_are_used(self):
        s = self.schedule
        self.assertIn("history-archive-source-permission-probe", s)
        self.assertIn("cancel-in-progress: false", s)
        self.assertIn("export PYTHONPATH=../archive-code/src", s)
        self.assertIn("python -m history_archive.v02_pr_body_pilot --recrawl-pr-body", s)
        self.assertIn("timeout-minutes: 20", s)
        self.assertIn("persist-credentials: false", s)

    def test_source_read_and_archive_write_permissions_remain_disjoint(self):
        s = self.schedule
        self.assertEqual(s.count("permission-pull-requests: read"), 1)
        self.assertEqual(s.count("permission-issues: read"), 1)
        self.assertEqual(s.count("permission-contents: write"), 1)
        self.assertIn("repositories: github-history-archive", s)
        self.assertNotIn("permission-pull-requests: write", s)
        self.assertNotIn("skip-token-revoke: true", s)
        self.assertNotIn("gh api graphql", s)

    def test_existing_v01_57_repo_schedule_is_unchanged(self):
        self.assertIn('cron: "11 * * * *"', self.fleet)
        self.assertIn('cron: "37 4 * * *"', self.fleet)
        self.assertIn("history-archive-hourly-fleet", self.fleet)
        self.assertIn("Fail run if a source was not fully checked", self.fleet)

if __name__ == "__main__":
    unittest.main()
