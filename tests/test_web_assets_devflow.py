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
        self.assertIn("view.auditSnapshot.hidden = !workflow", js)
        self.assertIn('block.addEventListener("toggle"', js)

    def test_human_portfolio_uses_independent_stable_read_only_queue_surface(self):
        html = (self.web_dir / "index.html").read_text(encoding="utf-8")
        js = (self.web_dir / "app.js").read_text(encoding="utf-8")
        css = (self.web_dir / "app.css").read_text(encoding="utf-8")

        self.assertIn('id="human-portfolio"', html)
        self.assertIn('id="human-portfolio-status"', html)
        self.assertIn('id="human-portfolio-grid"', html)

        self.assertIn("HUMAN_PORTFOLIO_LABELS", js)
        for disposition in (
            "READY",
            "IMPLEMENTING",
            "NEEDS_HUMAN",
            "WAIT_EXTERNAL",
            "NEEDS_EVIDENCE",
            "NEEDS_REVIEWER",
            "NEEDS_RECOVERY",
        ):
            self.assertIn(disposition, js)
        self.assertIn("const portfolioViews = new Map()", js)
        self.assertIn("function ensurePortfolioView", js)
        self.assertIn("function updatePortfolioView", js)
        self.assertIn("function reconcileHumanPortfolio", js)
        self.assertIn("currentState.human_portfolio", js)
        self.assertIn("safeWebUrl(entry.entry_ref)", js)
        self.assertIn("cache_freshness", js)
        self.assertIn("cache_complete", js)
        self.assertIn("provider_stale", js)
        self.assertNotIn("portfolioGrid.replaceChildren", js)

        self.assertIn(".human-portfolio", css)
        self.assertIn(".portfolio-grid", css)
        self.assertIn(".portfolio-item", css)
        self.assertIn(".portfolio-source-warning", css)

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
        self.assertIn(".audit-snapshot", css)


if __name__ == "__main__":
    unittest.main()
