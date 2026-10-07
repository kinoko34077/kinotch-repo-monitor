import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_ROOT = REPO_ROOT / "src" / "repo_monitor" / "pages"


class PagesUiRedesignContractTests(unittest.TestCase):
    def setUp(self):
        self.html = (PAGES_ROOT / "index.html").read_text(encoding="utf-8")
        self.css = (PAGES_ROOT / "pages.css").read_text(encoding="utf-8")
        self.js = (PAGES_ROOT / "pages.js").read_text(encoding="utf-8")

    def test_semantic_shell_is_compact_table_plus_inspector(self):
        for required in (
            'id="source-banner"',
            'id="summary-strip"',
            'id="filters"',
            'id="repository-table"',
            'id="repository-tbody"',
            'id="repository-mobile-list"',
            'id="repository-inspector"',
            'id="inspector-close"',
            'id="human-queue"',
        ):
            self.assertIn(required, self.html)

        self.assertIn("<table", self.html)
        self.assertIn("<thead", self.html)
        self.assertIn("<tbody", self.html)
        self.assertNotIn('class="repository-list"', self.html)
        self.assertNotIn('class="queue-list"', self.html)

    def test_filter_contract_includes_state_audit_sort_and_clear(self):
        for required in (
            'id="search"',
            'id="work-status"',
            'id="repository-state"',
            'id="audit-freshness"',
            'id="sort-order"',
            'id="clear-filters"',
        ):
            self.assertIn(required, self.html)

        for query_key in ('"q"', '"work"', '"state"', '"audit"', '"sort"'):
            self.assertIn(query_key, self.js)

    def test_repository_rows_do_not_expand_long_prose_inline(self):
        self.assertIn("renderRepositoryTable", self.js)
        self.assertIn("renderInspector", self.js)
        self.assertIn("match-reason", self.js)
        self.assertNotIn('"repository-card"', self.js)
        self.assertNotIn('"queue-card"', self.js)
        self.assertNotIn('"next-action"', self.js)
        self.assertNotIn('"active-work"', self.js)

    def test_human_queue_is_conditional_and_transport_warnings_are_visible(self):
        self.assertIn("humanQueueEntryCount", self.js)
        self.assertIn("nonCurrentPortfolioCount", self.js)
        self.assertIn("renderHumanQueue", self.js)
        self.assertIn("human-queue-warning", self.js)

    def test_selection_and_recovery_contract(self):
        for marker in (
            'addEventListener("keydown"',
            'event.key === "Escape"',
            "focusSelectedRepository",
            "setSelectedRepository",
            "loadState",
            "retry-load",
        ):
            self.assertIn(marker, self.js)

    def test_responsive_contract_restructures_mobile_instead_of_card_stack(self):
        self.assertIn("@media (max-width: 767px)", self.css)
        self.assertIn(".repository-mobile-list", self.css)
        self.assertIn(".repository-table-wrap", self.css)
        self.assertIn(".repository-inspector", self.css)
        self.assertNotIn(".repository-card", self.css)
        self.assertNotIn(".queue-card", self.css)

    def test_public_security_boundary_remains_read_only(self):
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn('method: "POST"', self.js)
        self.assertNotIn("/api/", self.js)
        self.assertNotIn("local_path", self.js)
        self.assertNotIn("chat_url", self.js)
        self.assertIn('parsed.protocol !== "https:"', self.js)
        self.assertIn('parsed.hostname !== "github.com"', self.js)


if __name__ == "__main__":
    unittest.main()
