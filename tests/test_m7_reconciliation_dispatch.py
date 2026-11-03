"""Operational PR-body reconciliation must be opt-in and independent of the Issue fleet."""
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / ".github/workflows/history-archive-fleet-hourly.yml"

class OperationalPRReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = FILE.read_text(encoding="utf-8")

    def test_one_source_operational_path_is_explicitly_opt_in(self):
        s = self.workflow
        self.assertIn("      pr_body_reconciliation:\n", s)
        self.assertIn("        default: false\n      pr_body_positive_canary:", s)
        self.assertIn("PR_BODY_RECONCILIATION: ${{ inputs.pr_body_reconciliation }}", s)
        self.assertIn('if [[ "$PR_BODY_RECONCILIATION" == "true" ]]; then', s)
        self.assertIn("python -m history_archive.v02_pr_body_pilot --recrawl-pr-body", s)

    def test_private_source_and_trusted_code_are_separate(self):
        s = self.workflow
        self.assertIn("path: m7-trusted-code", s)
        self.assertIn("persist-credentials: false", s)
        self.assertIn("ref: ${{ (inputs.pr_body_positive_canary || inputs.pr_body_reconciliation) && 'pilot/v02-multipage-pr-body-20261103' || 'main' }}", s)
        self.assertIn("export PYTHONPATH=../m7-trusted-code/src", s)
        self.assertIn("repositories: github-history-archive\n          permission-contents: write", s)
        self.assertIn("permission-pull-requests: read", s)
        self.assertNotIn("permission-pull-requests: write", s)

    def test_regular_57_source_fleet_stays_scheduled(self):
        s = self.workflow
        self.assertIn('cron: "11 * * * *"', s)
        self.assertIn('cron: "37 4 * * *"', s)
        self.assertIn("(!inputs.permission_probe && !inputs.review_archive_pilot && !inputs.pr_body_pages_pilot && !inputs.pr_body_positive_canary && !inputs.pr_body_reconciliation)", s)
        self.assertIn("history-archive-hourly-fleet", s)

if __name__ == "__main__":
    unittest.main()
