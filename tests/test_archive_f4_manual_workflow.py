"""F4 manual seven-kind archive workflow contract; no network calls."""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "history-archive-fleet-hourly.yml"


class ManualSevenKindWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_schedules_and_explicit_manual_gate(self):
        self.assertIn('cron: "11 * * * *"', self.content)
        self.assertIn('cron: "37 4 * * *"', self.content)
        self.assertIn("manual_all_seven:", self.content)
        self.assertIn("manual_reconcile_complete:", self.content)
        self.assertIn("manual_v02_pages:", self.content)
        self.assertIn('"$' + '{{ inputs.manual_all_seven }}" == "true"', self.content)

    def test_opt_in_five_lanes_and_safe_resume(self):
        section = self.content.split("\n  archive-v02-manual:\n", 1)[1]
        self.assertIn("github.event_name == 'workflow_dispatch'", section.splitlines()[0])
        self.assertIn("inputs.manual_all_seven", section.splitlines()[0])
        self.assertIn("for lane in pr-body pr-comment pr-review-body pr-review-comment commit-comment", section)
        self.assertIn("--source-index", section)
        self.assertIn("--lane", section)
        self.assertIn("--reconcile-complete", section)
        self.assertIn("state=$state", section)

    def test_existing_token_permissions_and_fail_closed(self):
        section = self.content.split("\n  archive-v02-manual:\n", 1)[1]
        self.assertIn("permission-issues: read", section)
        self.assertIn("permission-pull-requests: read", section)
        self.assertIn("permission-contents: write", section)
        self.assertIn("repositories: github-history-archive", section)
        self.assertNotIn("permission-actions: write", section)
        self.assertNotIn("permission-administration: write", section)
        self.assertIn("Unpushed private evidence prevents safe branch switch", section)
        self.assertIn("FAILED or UNAVAILABLE; no completion inferred", section)
        self.assertIn("if (( fail > 0 )); then", section)


if __name__ == "__main__":
    unittest.main()
