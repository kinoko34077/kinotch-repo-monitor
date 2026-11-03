from pathlib import Path
import unittest


FLEET = Path(__file__).resolve().parents[1] / ".github/workflows/history-archive-fleet-hourly.yml"


class FleetPRPermissionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = FLEET.read_text(encoding="utf-8")

    def test_probe_is_opt_in_and_skips_normal_collection(self):
        self.assertIn("      permission_probe:\n", self.text)
        self.assertIn("    if: ${{ github.event_name == 'workflow_dispatch' && (inputs.permission_probe || inputs.review_archive_pilot || inputs.pr_body_pages_pilot || inputs.pr_body_positive_canary || inputs.pr_body_reconciliation) }}", self.text)
        self.assertIn("    if: ${{ github.event_name != 'workflow_dispatch' || (!inputs.permission_probe && !inputs.review_archive_pilot && !inputs.pr_body_pages_pilot && !inputs.pr_body_positive_canary && !inputs.pr_body_reconciliation) }}", self.text)

    def test_private_review_pilot_is_opt_in_and_fails_closed(self):
        self.assertIn("      review_archive_pilot:", self.text)
        self.assertIn("        type: boolean", self.text)
        self.assertIn("        default: false", self.text)
        self.assertIn("history-archive-source-permission-probe", self.text)
        self.assertEqual(self.text.count("        if: ${{ inputs.review_archive_pilot }}"), 3)
        self.assertIn("git switch -q -c pilot/v02-source-app-edited-reviews-20261103", self.text)
        self.assertIn("python -m history_archive.v02_review_pilot", self.text)
        self.assertIn('if [[ "${#staged[@]}" -ne 4 ]]; then', self.text)
        self.assertIn('if [[ "$path" != archive/* ]]; then', self.text)
        self.assertIn("git push -q origin HEAD:refs/heads/pilot/v02-source-app-edited-reviews-20261103", self.text)
        self.assertIn("ARCHIVE_CHECKOUT_ROOT: .", self.text)
        self.assertNotIn("permission-contents: read", self.text)
        self.assertNotIn("git show", self.text)

    def test_two_page_m6_pilot_is_opt_in_and_isolated(self):
        self.assertIn("      pr_body_pages_pilot:", self.text)
        self.assertIn("        default: false", self.text)
        self.assertEqual(self.text.count("        if: ${{ inputs.pr_body_pages_pilot || inputs.pr_body_positive_canary || inputs.pr_body_reconciliation }}"), 3)
        self.assertIn("pilot/v02-multipage-pr-body-20261103", self.text)
        self.assertIn("python -m history_archive.v02_pr_body_pilot", self.text)
        self.assertIn("FLEET_SOURCE_TOKEN: ${{ steps.source-pr-read.outputs.token }}", self.text)
        self.assertIn("repositories: github-history-archive\n          permission-contents: write", self.text)
        self.assertIn("if: ${{ github.event_name != 'workflow_dispatch' || (!inputs.permission_probe && !inputs.review_archive_pilot && !inputs.pr_body_pages_pilot && !inputs.pr_body_positive_canary && !inputs.pr_body_reconciliation) }}", self.text)
        self.assertNotIn("permission-contents: read", self.text)
        self.assertNotIn("permission-pull-requests: write", self.text)

    def test_source_is_read_only_and_archive_write_stays_separate(self):
        self.assertEqual(self.text.count("permission-pull-requests: read"), 2)
        self.assertIn("permission-issues: read", self.text)
        self.assertNotIn("permission-pull-requests: write", self.text)
        self.assertIn("repositories: github-history-archive\n          permission-contents: write", self.text)
        self.assertNotIn("skip-token-revoke: true", self.text)

    def test_existing_schedule_and_source_collector_unchanged(self):
        self.assertIn('cron: "11 * * * *"', self.text)
        self.assertIn('cron: "37 4 * * *"', self.text)
        self.assertIn("history-archive-source-permission-probe", self.text)
        self.assertIn("history-archive-hourly-fleet", self.text)
        self.assertIn("--source-index", self.text)
        self.assertIn("Fail run if a source was not fully checked", self.text)

    def test_probe_does_not_print_private_source_text(self):
        self.assertIn("GH_TOKEN: ${{ steps.source-pr-read.outputs.token }}", self.text)
        self.assertIn("gh api graphql", self.text)
        self.assertIn("jq -e", self.text)
        self.assertIn("> /dev/null", self.text)


if __name__ == "__main__":
    unittest.main()
