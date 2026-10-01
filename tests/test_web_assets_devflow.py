import unittest
from pathlib import Path

import repo_monitor


class WebAssetDevflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web_dir = Path(repo_monitor.__file__).resolve().parent / "web"

    def test_javascript_renders_devflow_as_collapsed_details_with_short_preview(self):
        js = (self.web_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("DEVFLOW_STATUS_LABELS", js)
        self.assertIn("repo.devflow", js)
        self.assertIn("workflow-badge", js)
        self.assertIn("workflow-next-preview", js)
        self.assertIn('element("details"', js)
        self.assertIn('element("summary"', js)
        self.assertIn("active_work", js)
        self.assertIn("next_action", js)
        self.assertIn("expandedWorkflows", js)
        self.assertIn("audit_depth", js)
        self.assertIn("last_audit_at", js)
        self.assertIn("audit_freshness", js)
        self.assertIn("audit_evidence", js)
        self.assertIn("audit-snapshot", js)
        self.assertIn('block.addEventListener("toggle"', js)

    def test_javascript_exposes_remote_repo_action_and_human_age_units(self):
        js = (self.web_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("remote_web_url", js)
        self.assertIn('"Repo"', js)
        self.assertIn("日前", js)
        self.assertIn("か月前", js)

    def test_css_has_distinct_workflow_badge_and_collapsed_detail_styling(self):
        css = (self.web_dir / "app.css").read_text(encoding="utf-8")
        self.assertIn(".workflow-badge", css)
        self.assertIn("data-work-status", css)
        self.assertIn(".workflow-next-preview", css)
        self.assertIn(".workflow-details", css)


if __name__ == "__main__":
    unittest.main()
