"""Opt-in real-source PR-history canary must never affect the normal fleet."""
from pathlib import Path
import unittest

WF = Path(__file__).resolve().parents[1] / ".github/workflows/history-archive-fleet-hourly.yml"

class M7CanaryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WF.read_text(encoding="utf-8")

    def test_real_canary_is_explicit_dispatch_only(self):
        s = self.text
        self.assertIn("      pr_body_positive_canary:", s)
        self.assertIn("        default: false", s)
        self.assertIn("inputs.pr_body_pages_pilot || inputs.pr_body_positive_canary", s)
        self.assertIn("(!inputs.permission_probe && !inputs.review_archive_pilot && !inputs.pr_body_pages_pilot && !inputs.pr_body_positive_canary)", s)
        self.assertIn('cron: "11 * * * *"', s)
        self.assertIn('cron: "37 4 * * *"', s)

    def test_runs_accepted_main_code_over_existing_private_remote_cursor(self):
        s = self.text
        self.assertIn("path: m7-trusted-code", s)
        self.assertIn("persist-credentials: false", s)
        self.assertIn("ref: ${{ inputs.pr_body_positive_canary && 'pilot/v02-multipage-pr-body-20261103' || 'main' }}", s)
        self.assertIn("export PYTHONPATH=../m7-trusted-code/src", s)
        self.assertIn("python -m history_archive.v02_pr_body_pilot --resume-positive-canary", s)
        self.assertIn("git switch -q -C pilot/v02-multipage-pr-body-20261103", s)

    def test_permissions_and_non_canary_jobs_unchanged(self):
        s = self.text
        self.assertIn("permission-pull-requests: read", s)
        self.assertIn("repositories: github-history-archive\n          permission-contents: write", s)
        self.assertNotIn("permission-pull-requests: write", s)
        self.assertNotIn("permission-contents: read", s)

if __name__ == "__main__":
    unittest.main()
