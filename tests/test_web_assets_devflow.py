import unittest
from pathlib import Path

import repo_monitor


class WebAssetDevflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web_dir = Path(repo_monitor.__file__).resolve().parent / "web"

    def test_javascript_renders_devflow_work_status_as_separate_workflow_badge(self):
        js = (self.web_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("DEVFLOW_STATUS_LABELS", js)
        self.assertIn("repo.devflow", js)
        self.assertIn("workflow-badge", js)
        self.assertIn("active_work", js)
        self.assertIn("next_action", js)

    def test_css_has_distinct_workflow_badge_styling(self):
        css = (self.web_dir / "app.css").read_text(encoding="utf-8")
        self.assertIn(".workflow-badge", css)
        self.assertIn("data-work-status", css)


if __name__ == "__main__":
    unittest.main()
