import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from repo_monitor.devflow_state import (
    DevflowRepoState,
    DevflowSnapshot,
    HumanPortfolioEntry,
    HumanPortfolioState,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "build_pages.py"
SPEC = importlib.util.spec_from_file_location("build_pages", MODULE_PATH)
build_pages = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_pages)


class PagesBuildTests(unittest.TestCase):
    def _snapshot(self):
        return DevflowSnapshot(
            repositories={
                "example": DevflowRepoState(
                    repository="example",
                    repository_full_name="kinoko34077/example",
                    work_status="IMPLEMENTING",
                    repository_state="ACTIVE",
                    active_work="kinoko34077/example#7",
                    next_action="VERIFY",
                    issue_number=59,
                    issue_url="https://github.com/kinoko34077/devflow/issues/59",
                    updated_at="2026-10-06T02:00:00Z",
                    audit_sha="a" * 40,
                    audit_ref="main",
                    audit_depth="STANDARD",
                    audit_freshness="CURRENT",
                )
            },
            fetched_at=1791252000.0,
            error=None,
            stale=False,
            human_portfolios={
                "kinoko34077/example": HumanPortfolioState(
                    repository="kinoko34077/example",
                    observed_at="2026-10-06T01:59:00Z",
                    generated_at="2026-10-06T02:00:00Z",
                    valid_until="2026-10-07T02:00:00Z",
                    generation_id="sha256:" + ("b" * 64),
                    complete=True,
                    transport_status="CURRENT",
                    repository_source={
                        "status": "AVAILABLE",
                        "freshness": "CURRENT",
                        "error": None,
                    },
                    reconciliation_source={
                        "status": "AVAILABLE",
                        "trust": "VERIFIED",
                        "control_issue_number": 59,
                        "control_url": "https://github.com/kinoko34077/devflow/issues/59",
                        "error": None,
                        "task_errors": [],
                    },
                    entries=(
                        HumanPortfolioEntry(
                            repository="kinoko34077/example",
                            task_ref="kinoko34077/example#7",
                            entry_ref="https://github.com/kinoko34077/example/issues/7",
                            disposition="IMPLEMENTING",
                            role="TASK",
                            source_kind="REPOSITORY_PROJECTION",
                            observed_at="2026-10-06T01:59:00Z",
                            work_status="IMPLEMENTING",
                            publication_id=None,
                            evidence_freshness="CURRENT",
                            evidence_trust="VERIFIED",
                        ),
                    ),
                )
            },
        )

    def test_public_snapshot_contains_only_devflow_owned_public_dimensions(self):
        payload = build_pages.build_public_snapshot(
            self._snapshot(),
            generated_at=datetime(2026, 10, 6, 2, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(payload["schema_version"], "repo-monitor-pages.v1")
        self.assertEqual(payload["source"]["kind"], "public-devflow-controls")
        self.assertEqual(
            payload["repositories"][0]["repository_full_name"],
            "kinoko34077/example",
        )
        self.assertEqual(
            payload["human_portfolios"][0]["entries"][0]["task_ref"],
            "kinoko34077/example#7",
        )

        serialized = json.dumps(payload, sort_keys=True)
        for forbidden in (
            "chat_url",
            "local_path",
            '"path"',
            '"dirty"',
            '"ahead"',
            '"behind"',
            "changed_count",
            "latest_mtime",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_write_site_emits_static_artifact_and_no_backend_contract(self):
        payload = build_pages.build_public_snapshot(
            self._snapshot(),
            generated_at=datetime(2026, 10, 6, 2, 1, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            build_pages.write_site(output, payload)

            self.assertTrue((output / ".nojekyll").is_file())
            self.assertEqual(
                json.loads((output / "state.json").read_text(encoding="utf-8")),
                payload,
            )
            html = (output / "index.html").read_text(encoding="utf-8")
            js = (output / "pages.js").read_text(encoding="utf-8")
            self.assertIn("Public Development Dashboard", html)
            self.assertIn('fetch("./state.json"', js)
            self.assertNotIn("innerHTML", js)
            self.assertNotIn('method: "POST"', js)
            self.assertNotIn("/api/", js)
            self.assertNotIn("chat_url", html.casefold())
            self.assertNotIn("chat_url", js.casefold())

    def test_pages_workflow_is_actions_deploy_and_immutable_pinned(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "pages.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("permissions:\n      contents: read", workflow)
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("python tools/build_pages.py --output _site", workflow)
        self.assertIn(
            "actions/configure-pages@983d7736d9b0ae728b81ab479565c72886d7745b",
            workflow,
        )
        self.assertIn(
            "actions/upload-pages-artifact@56afc609e74202658d3ffba0e8f6dda462b719fa",
            workflow,
        )
        self.assertIn(
            "actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
            workflow,
        )
        self.assertIn("url: ${{ steps.deployment.outputs.page_url }}", workflow)
        self.assertNotIn(r"url: \${{", workflow)
        self.assertNotIn("enablement:", workflow)


if __name__ == "__main__":
    unittest.main()
