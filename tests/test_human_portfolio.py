import copy
import hashlib
import json
import unittest

from repo_monitor.human_portfolio import (
    HUMAN_PORTFOLIO_MARKER_BEGIN,
    HUMAN_PORTFOLIO_MARKER_END,
    parse_human_portfolio_transport,
)


REPOSITORY = "kinoko34077/example-repo"
OBSERVED_AT = "2026-10-06T01:00:00Z"
GENERATED_AT = "2026-10-06T01:01:00Z"
VALID_UNTIL = "2026-10-07T01:01:00Z"
NOW = 1791249000.0


def canonical_generation(payload):
    material = copy.deepcopy(payload)
    material.pop("generation_id", None)
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def payload():
    value = {
        "schema_version": "human-portfolio-cache.v1",
        "repository": REPOSITORY,
        "observed_at": OBSERVED_AT,
        "generated_at": GENERATED_AT,
        "valid_until": VALID_UNTIL,
        "generation_id": "",
        "complete": True,
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
        "entries": [
            {
                "repository": REPOSITORY,
                "task_ref": REPOSITORY + "#32",
                "entry_ref": "https://github.com/kinoko34077/example-repo/issues/32",
                "disposition": "NEEDS_REVIEWER",
                "role": "reviewer",
                "source_kind": "RECONCILIATION",
                "observed_at": OBSERVED_AT,
                "work_status": None,
                "publication_id": "sha256:" + ("a" * 64),
                "evidence_freshness": "CURRENT",
                "evidence_trust": "VERIFIED",
            },
            {
                "repository": REPOSITORY,
                "task_ref": REPOSITORY + "#33",
                "entry_ref": "https://github.com/kinoko34077/example-repo/issues/33",
                "disposition": "NEEDS_HUMAN",
                "role": "implementer",
                "source_kind": "REPOSITORY_PROJECTION",
                "observed_at": OBSERVED_AT,
                "work_status": "BLOCKED",
                "publication_id": None,
                "evidence_freshness": "CURRENT",
                "evidence_trust": "VERIFIED",
            },
        ],
    }
    value["generation_id"] = canonical_generation(value)
    return value


def marker(value=None):
    value = payload() if value is None else value
    return (
        HUMAN_PORTFOLIO_MARKER_BEGIN
        + "\n"
        + json.dumps(value, sort_keys=True)
        + "\n"
        + HUMAN_PORTFOLIO_MARKER_END
    )


class HumanPortfolioTransportTests(unittest.TestCase):
    def test_valid_marker_preserves_producer_entries_without_reclassification(self):
        state = parse_human_portfolio_transport(marker(), REPOSITORY, now=NOW)

        self.assertIsNotNone(state)
        self.assertEqual(state.repository, REPOSITORY)
        self.assertEqual(state.cache_freshness, "CURRENT")
        self.assertTrue(state.complete)
        self.assertEqual(
            [entry["disposition"] for entry in state.entries],
            ["NEEDS_REVIEWER", "NEEDS_HUMAN"],
        )
        self.assertEqual(
            state.entries[0]["entry_ref"],
            "https://github.com/kinoko34077/example-repo/issues/32",
        )
        self.assertEqual(state.generated_at, GENERATED_AT)
        self.assertEqual(state.valid_until, VALID_UNTIL)

    def test_missing_marker_is_optional(self):
        self.assertIsNone(
            parse_human_portfolio_transport(
                "## Repository\n\nkinoko34077/example-repo\n",
                REPOSITORY,
                now=NOW,
            )
        )

    def test_expired_marker_is_stale_but_entries_remain_visible_evidence(self):
        value = payload()
        value["observed_at"] = "2026-10-04T01:00:00Z"
        value["generated_at"] = "2026-10-04T01:01:00Z"
        value["valid_until"] = "2026-10-05T01:01:00Z"
        for entry in value["entries"]:
            entry["observed_at"] = "2026-10-04T01:00:00Z"
        value["generation_id"] = canonical_generation(value)

        state = parse_human_portfolio_transport(marker(value), REPOSITORY, now=NOW)

        self.assertEqual(state.cache_freshness, "STALE")
        self.assertEqual(len(state.entries), 2)

    def test_unavailable_or_invalid_sources_remain_explicit(self):
        unavailable = payload()
        unavailable["complete"] = False
        unavailable["repository_source"] = {
            "status": "UNAVAILABLE",
            "freshness": "UNKNOWN",
            "error": "read failed",
        }
        unavailable["entries"] = []
        unavailable["generation_id"] = canonical_generation(unavailable)
        self.assertEqual(
            parse_human_portfolio_transport(
                marker(unavailable), REPOSITORY, now=NOW
            ).cache_freshness,
            "UNAVAILABLE",
        )

        invalid = payload()
        invalid["complete"] = False
        invalid["reconciliation_source"] = {
            "status": "INVALID",
            "trust": "UNKNOWN",
            "control_issue_number": 59,
            "control_url": "https://github.com/kinoko34077/devflow/issues/59",
            "error": "malformed publication",
            "task_errors": [],
        }
        invalid["entries"] = invalid["entries"][1:]
        invalid["generation_id"] = canonical_generation(invalid)
        self.assertEqual(
            parse_human_portfolio_transport(
                marker(invalid), REPOSITORY, now=NOW
            ).cache_freshness,
            "INVALID",
        )

    def test_generation_tamper_fails_closed(self):
        value = payload()
        value["complete"] = False

        with self.assertRaisesRegex(ValueError, "generation_id"):
            parse_human_portfolio_transport(marker(value), REPOSITORY, now=NOW)

    def test_entry_link_must_match_exact_task(self):
        value = payload()
        value["entries"][0]["entry_ref"] = (
            "https://github.com/kinoko34077/example-repo/issues/99"
        )
        value["generation_id"] = canonical_generation(value)

        with self.assertRaisesRegex(ValueError, "exact owning task"):
            parse_human_portfolio_transport(marker(value), REPOSITORY, now=NOW)

    def test_duplicate_json_keys_and_duplicate_marker_pairs_fail_closed(self):
        text = marker().replace(
            '"complete": true',
            '"complete": true, "complete": false',
            1,
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            parse_human_portfolio_transport(text, REPOSITORY, now=NOW)

        with self.assertRaisesRegex(ValueError, "exactly one marker pair"):
            parse_human_portfolio_transport(marker() + "\n" + marker(), REPOSITORY, now=NOW)


if __name__ == "__main__":
    unittest.main()
