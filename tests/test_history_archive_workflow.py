from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "history-archive.yml"


class HistoryArchiveWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_source_github_token_is_read_only_and_repository_scoped(self):
        self.assertIn("permissions:\n  contents: read\n  issues: read", self.text)
        self.assertNotIn("permissions: write-all", self.text)
        self.assertIn("SOURCE_GITHUB_TOKEN: ${{ github.token }}", self.text)

    def test_archive_app_token_is_limited_to_archive_contents_write(self):
        self.assertIn(
            "uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3",
            self.text,
        )
        self.assertIn("repositories: github-history-archive", self.text)
        self.assertIn("permission-contents: write", self.text)
        self.assertIn("client-id: ${{ vars.HISTORY_ARCHIVE_APP_CLIENT_ID }}", self.text)
        self.assertIn("private-key: ${{ secrets.HISTORY_ARCHIVE_APP_PRIVATE_KEY }}", self.text)

    def test_tail_is_filtered_to_current_source_repository(self):
        self.assertIn('--repository "${{ github.repository }}"', self.text)

    def test_pr_conversation_comments_are_filtered_before_job_execution(self):
        self.assertIn("github.event.issue.pull_request == null", self.text)

    def test_archive_commit_fails_closed_on_unexpected_paths(self):
        self.assertIn("grep -Ev '^(archive|tracking)/'", self.text)
        self.assertIn("Unexpected changed paths; refusing archive commit", self.text)

    def test_same_issue_events_share_one_concurrency_group(self):
        self.assertIn(
            "group: history-archive-${{ github.repository }}-${{ github.event.issue.number || github.run_id }}",
            self.text,
        )
        self.assertNotIn("github.event.comment.id", self.text)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertNotIn("group: history-archive-${{ github.repository }}\n", self.text)

    def test_secret_bearing_actions_are_immutable_sha_pinned(self):
        self.assertIn(
            "uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3",
            self.text,
        )
        self.assertIn(
            "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6",
            self.text,
        )
        self.assertNotIn("uses: actions/create-github-app-token@v3", self.text)
        self.assertNotIn("uses: actions/checkout@v6", self.text)

    def test_archive_push_has_bounded_contention_retry(self):
        self.assertIn("for attempt in 1 2 3 4; do", self.text)
        self.assertIn("git pull --rebase origin main", self.text)
        self.assertIn("git push origin HEAD:main", self.text)
        self.assertIn("git rebase --abort", self.text)
        self.assertIn("Archive push failed after 4 attempts", self.text)


if __name__ == "__main__":
    unittest.main()
