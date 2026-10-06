import hashlib
import json
import unittest
from datetime import datetime

from repo_monitor.devflow_state import DevflowStateProvider


ISSUE_BODY = """## Repository

`kinoko34077/example-repo`

## Work Status

`IMPLEMENTING`

## Repository State

`ACTIVE`

## Active Work

`example-repo#12` — implement.

## Next Action

`VERIFY`
"""


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def entry(
    number,
    disposition,
    *,
    role="TASK",
    source_kind="REPOSITORY_PROJECTION",
    publication_id=None,
):
    return {
        "repository": "kinoko34077/example-repo",
        "task_ref": f"kinoko34077/example-repo#{number}",
        "entry_ref": f"https://github.com/kinoko34077/example-repo/issues/{number}",
        "disposition": disposition,
        "role": role,
        "source_kind": source_kind,
        "observed_at": "2026-10-06T00:55:00Z",
        "work_status": "IMPLEMENTING" if disposition == "IMPLEMENTING" else None,
        "publication_id": publication_id,
        "evidence_freshness": "CURRENT",
        "evidence_trust": "VERIFIED",
    }


def human_portfolio_transport(
    *,
    generated_at="2026-10-06T01:00:00Z",
    valid_until="2026-10-07T01:00:00Z",
    complete=True,
    corrupt_generation=False,
    entries=None,
):
    payload = {
        "schema_version": "human-portfolio-cache.v1",
        "repository": "kinoko34077/example-repo",
        "observed_at": "2026-10-06T00:55:00Z",
        "generated_at": generated_at,
        "valid_until": valid_until,
        "generation_id": "",
        "complete": complete,
        "repository_source": {
            "status": "AVAILABLE",
            "freshness": "CURRENT",
            "error": None,
        },
        "reconciliation_source": {
            "status": "AVAILABLE",
            "trust": "VERIFIED",
            "control_issue_number": 59,
            "control_url": "https://github.com/kinoko34077/devflow/issues/59",
            "error": None,
            "task_errors": [],
        },
        "entries": list(entries or []),
    }
    material = dict(payload)
    material.pop("generation_id")
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    payload["generation_id"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if corrupt_generation:
        payload["generation_id"] = "sha256:" + ("0" * 64)
    return (
        "\n\n<!-- DEVFLOW_HUMAN_PORTFOLIO_V1_BEGIN -->\n"
        + json.dumps(payload, sort_keys=True)
        + "\n<!-- DEVFLOW_HUMAN_PORTFOLIO_V1_END -->"
    )


def issue_with_portfolio(**kwargs):
    return {
        "number": 59,
        "title": "[REPO] example-repo",
        "body": ISSUE_BODY + human_portfolio_transport(**kwargs),
        "html_url": "https://github.com/kinoko34077/devflow/issues/59",
        "updated_at": "2026-10-06T01:00:00Z",
        "author_association": "OWNER",
        "labels": [],
    }


class HumanPortfolioStateTests(unittest.TestCase):
    def test_current_cache_preserves_multiple_entries_without_reclassification(self):
        rows = [
            entry(12, "IMPLEMENTING"),
            entry(
                13,
                "NEEDS_REVIEWER",
                role="reviewer",
                source_kind="RECONCILIATION",
                publication_id="sha256:" + ("a" * 64),
            ),
        ]
        provider = DevflowStateProvider(
            fetcher=lambda: [issue_with_portfolio(entries=rows)],
            clock=lambda: epoch("2026-10-06T01:05:00Z"),
        )

        snapshot = provider.snapshot()
        portfolio = snapshot.human_portfolios["kinoko34077/example-repo"]

        self.assertEqual(portfolio.transport_status, "CURRENT")
        self.assertTrue(portfolio.current)
        self.assertEqual(
            [item.disposition for item in portfolio.entries],
            ["IMPLEMENTING", "NEEDS_REVIEWER"],
        )
        self.assertEqual(portfolio.entries[1].role, "reviewer")
        self.assertEqual(
            portfolio.entries[1].entry_ref,
            "https://github.com/kinoko34077/example-repo/issues/13",
        )

    def test_incomplete_cache_is_visible_and_not_current(self):
        provider = DevflowStateProvider(
            fetcher=lambda: [
                issue_with_portfolio(
                    complete=False,
                    entries=[entry(12, "NEEDS_EVIDENCE")],
                )
            ],
            clock=lambda: epoch("2026-10-06T01:05:00Z"),
        )

        snapshot = provider.snapshot()
        portfolio = snapshot.human_portfolios["kinoko34077/example-repo"]

        self.assertEqual(portfolio.transport_status, "INCOMPLETE")
        self.assertFalse(portfolio.current)
        self.assertFalse(portfolio.complete)
        self.assertEqual(portfolio.entries[0].disposition, "NEEDS_EVIDENCE")

    def test_expired_cache_is_retained_as_stale_not_promoted_current(self):
        provider = DevflowStateProvider(
            fetcher=lambda: [
                issue_with_portfolio(
                    generated_at="2026-10-06T01:00:00Z",
                    valid_until="2026-10-07T01:00:00Z",
                    entries=[entry(12, "IMPLEMENTING")],
                )
            ],
            clock=lambda: epoch("2026-10-08T01:05:00Z"),
        )

        snapshot = provider.snapshot()
        portfolio = snapshot.human_portfolios["kinoko34077/example-repo"]

        self.assertEqual(portfolio.transport_status, "STALE")
        self.assertFalse(portfolio.current)
        self.assertEqual(portfolio.entries[0].disposition, "IMPLEMENTING")

    def test_generation_tamper_preserves_last_good_and_marks_snapshot_stale(self):
        calls = [0]
        now = [epoch("2026-10-06T01:05:00Z")]

        def fetcher():
            calls[0] += 1
            return [
                issue_with_portfolio(
                    corrupt_generation=calls[0] > 1,
                    entries=[entry(12, "IMPLEMENTING")],
                )
            ]

        provider = DevflowStateProvider(
            fetcher=fetcher,
            clock=lambda: now[0],
            ttl_seconds=120.0,
            retry_seconds=30.0,
        )
        first = provider.snapshot()
        now[0] += 121.0
        failed = provider.snapshot()

        self.assertFalse(first.stale)
        self.assertTrue(failed.stale)
        self.assertIn("generation_id", failed.error)
        self.assertEqual(failed.human_portfolios, first.human_portfolios)


if __name__ == "__main__":
    unittest.main()
