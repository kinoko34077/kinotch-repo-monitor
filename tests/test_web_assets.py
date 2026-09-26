import unittest
from pathlib import Path

import repo_monitor


class WebAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web_dir = Path(repo_monitor.__file__).resolve().parent / "web"

    def test_index_exposes_dashboard_hooks_and_external_assets(self):
        html = (self.web_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="repo-grid"', html)
        self.assertIn('id="status-line"', html)
        self.assertIn('id="repo-add-button"', html)
        self.assertIn('id="repo-add-dialog"', html)
        self.assertIn('id="rediscover-button"', html)
        self.assertIn('href="/app.css"', html)
        self.assertIn('src="/app.js"', html)

    def test_css_uses_responsive_grid_instead_of_fixed_five_columns(self):
        css = (self.web_dir / "app.css").read_text(encoding="utf-8")
        self.assertIn("display: grid", css)
        self.assertIn("auto-fit", css)
        self.assertIn("minmax", css)
        self.assertIn("data-status", css)

    def test_javascript_uses_api_routes_and_safe_dom_text_rendering(self):
        js = (self.web_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/state", js)
        self.assertIn("/api/rediscover", js)
        self.assertIn("/api/repos/add", js)
        self.assertIn("encodeURIComponent", js)
        self.assertIn("textContent", js)
        self.assertNotIn("innerHTML", js)

    def test_repository_card_click_opens_registered_chat_or_registration_dialog(self):
        js = (self.web_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn('card.addEventListener("click", () => openChat(repo))', js)


if __name__ == "__main__":
    unittest.main()
