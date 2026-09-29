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
        self.assertIn("uses: actions/create-github-app-token@v3", self.text)
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


if __name__ == "__main__":
    unittest.main()
