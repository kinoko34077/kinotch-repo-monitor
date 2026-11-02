from pathlib import Path
import unittest


FLEET = Path(__file__).resolve().parents[1] / ".github/workflows/history-archive-fleet-hourly.yml"


class FleetPRPermissionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = FLEET.read_text(encoding="utf-8")

    def test_probe_is_opt_in_and_skips_normal_collection(self):
        self.assertIn("      permission_probe:\n", self.text)
        self.assertIn("    if: ${{ github.event_name == 'workflow_dispatch' && inputs.permission_probe }}", self.text)
        self.assertIn("    if: ${{ github.event_name != 'workflow_dispatch' || !inputs.permission_probe }}", self.text)

    def test_source_is_read_only_and_archive_write_stays_separate(self):
        self.assertEqual(self.text.count("permission-pull-requests: read"), 2)
        self.assertIn("permission-issues: read", self.text)
        self.assertNotIn("permission-pull-requests: write", self.text)
        self.assertIn("repositories: github-history-archive\n          permission-contents: write", self.text)
        self.assertNotIn("skip-token-revoke: true", self.text)

    def test_commit_comment_node_read_is_explicit_opt_in_without_logging_fixture(self):
        self.assertIn("      commit_comment_probe_node_id:", self.text)
        self.assertIn("        required: false", self.text)
        self.assertIn("          COMMIT_PROBE_ID: ${{ inputs.commit_comment_probe_node_id }}", self.text)
        self.assertIn('if [[ -n "$COMMIT_PROBE_ID" ]]; then', self.text)
        self.assertIn("... on CommitComment{id repository{nameWithOwner} commit{oid} userContentEdits", self.text)
        self.assertIn(".data.node.userContentEdits.totalCount >= 2", self.text)
        self.assertNotIn("CC_kwDOUvlpyM4MYjkS", self.text)
        self.assertNotIn("permission-contents: read", self.text)

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
