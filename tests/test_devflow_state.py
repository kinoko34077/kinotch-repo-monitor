import hashlib
import json
import os
import threading
import time
import unittest
from email.message import Message
from datetime import datetime
from unittest.mock import patch
from urllib.error import HTTPError

from repo_monitor.devflow_state import (
    DevflowStateProvider, _fetch_public_issues, parse_control_issues,
    _parse_cached_all_state,
)


ISSUE_BODY = """## Repository

`kinoko34077/example-repo`

## Work Status

`IMPLEMENTING`

## Type

`FEATURE`

## Repository State

`ACTIVE`

## Audit SHA

`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`

## Audit Ref

`main`

## Last Audit At

`2026-10-01T09:02:38Z`

## Audit Depth

`CONTROL`

## Audit Scope

`Stage-2 fleet control audit`

## Audit Evidence

`run 36840152955 / artifact 11150403935`

## Last Deep Audit At

`2026-09-29T04:05:00Z`


## Active Work

`example-repo#12` — implement the feature.

## Next Action

`VERIFY — run CI`
"""


def all_state_transport(
    *,
    statuses=("AWAITING_REVIEW", "BLOCKED"),
    mode="COMPLETE",
    corrupt=False,
    repository="kinoko34077/example-repo",
):
    marker = projection_transport()
    raw = marker.split("<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_BEGIN -->", 1)[1]
    raw = raw.split("<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_END -->", 1)[0]
    payload = json.loads(raw)
    rows = [
        {
            "issue_number": index, "title": f"Real TASK {index}",
            "url": f"https://github.com/{repository}/issues/{index}",
            "source_kind": "MACHINE", "record_role": "TASK",
            "type": "FEATURE", "work_status": status,
            "attention_disposition": None,
        }
        for index, status in enumerate(statuses, 1)
    ]
    payload["counts"]["open_issues"] = len(statuses)
    payload["counts"]["machine_records"] = len(statuses)
    payload["counts"]["machine_tasks"] = len(statuses)
    payload["all_state_tasks"] = {
        "status": mode,
        "total": len(statuses),
        "records": rows[:20],
    }
    if corrupt:
        payload["all_state_tasks"]["records"][0]["url"] = "javascript:alert(1)"
    material = dict(payload)
    material.pop("generation_id")
    payload["generation_id"] = "sha256:" + hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return (
        "<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_BEGIN -->\n"
        + json.dumps(payload)
        + "\n<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_END -->"
    )


def issue_payload():
    return [
        {
            "number": 59,
            "title": "[REPO] example-repo",
            "body": ISSUE_BODY,
            "html_url": "https://github.com/kinoko34077/devflow/issues/59",
            "updated_at": "2026-09-26T03:00:00Z",
            "author_association": "OWNER",
            "user": {"id": 79015263, "login": "kinoko34077"},
            "labels": [{"name": "devflow:audit-freshness:current"}],
        }
    ]


def projection_transport(
    *,
    repository="kinoko34077/example-repo",
    generated_at="2026-10-04T05:50:00Z",
    valid_until="2026-10-05T05:50:00Z",
    source_status="AVAILABLE",
    source_freshness="CURRENT",
    trust_status="VERIFIED",
    trust_freshness="CURRENT",
    trust_source="DEVFLOW_SHARED_CONTROL_VERIFIER",
    corrupt_generation=False,
):
    payload = {
        "schema_version": "repository-projection-cache.v1",
        "repository": repository,
        "generated_at": generated_at,
        "valid_until": valid_until,
        "generation_id": "",
        "source": {
            "status": source_status,
            "freshness": source_freshness,
            "observed_at": "2026-10-04T05:49:00Z",
            "error": None,
            "digest": "sha256:" + ("b" * 64),
        },
        "coverage": {
            "status": "COMPLETE",
            "ambiguous": False,
            "active_work_evidence": "NO_MACHINE_TASKS_UNDER_COMPLETE_COVERAGE",
            "can_replace_manual_active_work": False,
        },
        "counts": {
            "open_issues": 0,
            "machine_records": 0,
            "machine_tasks": 0,
            "legacy_hints": 0,
            "unclassified": 0,
            "invalid_metadata": 0,
            "untrusted_metadata": 0,
        },
        "type_counts": {"machine": {}, "legacy_hint": {}},
        "tasks": {"ready": [], "implementing": []},
        "references": {"newest_open_issue": None, "recently_active_issue": None},
        "control_trust": {
            "status": trust_status,
            "freshness": trust_freshness,
            "source": trust_source,
            "observed_at": "2026-10-04T05:49:00Z",
            "detail": None,
        },
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
        "\n\n<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_BEGIN -->\n"
        + json.dumps(payload, sort_keys=True)
        + "\n<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_END -->"
    )


class M3AllStateTransportTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat("2026-10-04T06:00:00+00:00").timestamp()

    def test_current_complete_has_review_and_blocked_and_no_local_classification(self):
        value = _parse_cached_all_state(
            all_state_transport(), "kinoko34077/example-repo", now=self.now,
        )
        self.assertEqual(value["transport_status"], "CURRENT")
        self.assertEqual(value["status"], "COMPLETE")
        self.assertEqual(value["total"], 2)
        self.assertEqual(
            [item["work_status"] for item in value["records"]],
            ["AWAITING_REVIEW", "BLOCKED"],
        )
        issue = issue_payload()[0]
        issue["body"] += "\n" + all_state_transport()
        from repo_monitor.devflow_state import _parse_control_data
        states, _ = _parse_control_data([issue], now=self.now)
        self.assertEqual(states["example-repo"].as_dict()["all_state_tasks"], value)

    def test_missing_or_historical_field_is_unknown_not_zero(self):
        self.assertEqual(
            _parse_cached_all_state(ISSUE_BODY, "kinoko34077/example-repo", now=self.now)["status"],
            "UNKNOWN",
        )
        self.assertEqual(
            _parse_cached_all_state(projection_transport(), "kinoko34077/example-repo", now=self.now)["status"],
            "UNKNOWN",
        )

    def test_stale_or_corrupted_cache_fails_closed_without_executability(self):
        self.assertEqual(
            _parse_cached_all_state(all_state_transport(), "kinoko34077/example-repo", now=self.now + 90000)["transport_status"],
            "STALE",
        )
        for raw in (
            all_state_transport(corrupt=True),
            all_state_transport(repository="kinoko34077/other"),
            all_state_transport(mode="COMPLETE", statuses=tuple("BLOCKED" for _ in range(21))),
        ):
            with self.subTest(sample=raw[-100:]):
                value = _parse_cached_all_state(raw, "kinoko34077/example-repo", now=self.now)
                self.assertEqual(value["transport_status"], "INVALID")
                self.assertEqual(value["records"], [])

    def test_21_tasks_truncated_is_visible_as_partial_not_complete(self):
        value = _parse_cached_all_state(
            all_state_transport(mode="TRUNCATED", statuses=tuple("BLOCKED" for _ in range(21))),
            "kinoko34077/example-repo", now=self.now,
        )
        self.assertEqual(value["status"], "TRUNCATED")
        self.assertEqual(value["total"], 21)
        self.assertEqual(len(value["records"]), 20)

class DevflowStateTests(unittest.TestCase):
    def test_parse_control_issues_extracts_repository_workflow_fields(self):
        issues = issue_payload() + [
            {
                "number": 60,
                "title": "[SYSTEM] ignore me",
                "body": "not a repository control issue",
                "html_url": "https://github.com/kinoko34077/devflow/issues/60",
                "author_association": "OWNER",
            },
        ]

        states = parse_control_issues(issues)

        self.assertEqual(list(states), ["example-repo"])
        state = states["example-repo"]
        self.assertEqual(state.repository_full_name, "kinoko34077/example-repo")
        self.assertEqual(state.work_status, "IMPLEMENTING")
        self.assertEqual(state.repository_state, "ACTIVE")
        self.assertEqual(state.audit_sha, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(state.audit_ref, "main")
        self.assertEqual(state.last_audit_at, "2026-10-01T09:02:38Z")
        self.assertEqual(state.audit_depth, "CONTROL")
        self.assertEqual(state.audit_scope, "Stage-2 fleet control audit")
        self.assertEqual(state.audit_evidence, "run 36840152955 / artifact 11150403935")
        self.assertEqual(state.last_deep_audit_at, "2026-09-29T04:05:00Z")
        self.assertEqual(state.audit_freshness, "CURRENT")
        self.assertEqual(state.active_work, "example-repo#12 — implement the feature.")
        self.assertEqual(state.next_action, "VERIFY — run CI")
        self.assertEqual(state.issue_number, 59)
        self.assertEqual(state.issue_url, "https://github.com/kinoko34077/devflow/issues/59")
        self.assertEqual(state.updated_at, "2026-09-26T03:00:00Z")

    def test_direct_trusted_control_rejects_title_body_repository_identity_mismatch(self):
        issue = {
            **issue_payload()[0],
            "title": "[REPO] other-repo",
        }

        with self.assertRaisesRegex(ValueError, "repository identity"):
            parse_control_issues([issue])

    def test_parse_control_issues_ignores_untrusted_and_pull_request_items(self):
        trusted = issue_payload()[0]
        untrusted = {
            **trusted,
            "number": 60,
            "title": "[REPO] attacker-repo",
            "author_association": "NONE",
        }
        unknown = {
            key: value
            for key, value in {
                **trusted,
                "number": 61,
                "title": "[REPO] unknown-repo",
            }.items()
            if key != "author_association"
        }
        pull_request = {
            **trusted,
            "number": 62,
            "title": "[REPO] pr-lookalike",
            "pull_request": {"url": "https://api.github.com/repos/x/y/pulls/62"},
        }

        states = parse_control_issues([untrusted, unknown, pull_request, trusted])

        self.assertEqual(list(states), ["example-repo"])

    def test_direct_control_trust_requires_numeric_principal_not_association_alone(self):
        cases = (
            ("missing-user", None),
            ("empty-user", {}),
            ("unlisted-id", {"id": 79015264, "login": "some-collaborator"}),
            ("bool-id", {"id": True, "login": "kinoko34077"}),
            ("string-id", {"id": "79015263", "login": "kinoko34077"}),
            ("missing-id", {"login": "kinoko34077"}),
            ("login-mismatch", {"id": 79015263, "login": "different-user"}),
            ("login-absent", {"id": 79015263}),
        )
        for name, user in cases:
            with self.subTest(case=name):
                issue = {**issue_payload()[0], "author_association": "COLLABORATOR"}
                if user is None:
                    issue.pop("user")
                else:
                    issue["user"] = user
                self.assertEqual(parse_control_issues([issue]), {})

        # Association remains defense in depth, not principal authority.
        valid = {**issue_payload()[0], "author_association": "COLLABORATOR"}
        self.assertEqual(list(parse_control_issues([valid])), ["example-repo"])
        missing_association = {**valid, "author_association": "NONE"}
        self.assertEqual(parse_control_issues([missing_association]), {})

    def test_bootstrap_bot_control_with_current_verified_projection_is_accepted(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + projection_transport(),
        }

        states = parse_control_issues([issue], now=1791097200.0)

        self.assertEqual(list(states), ["example-repo"])
        self.assertEqual(states["example-repo"].issue_number, 59)

    def test_bootstrap_bot_control_title_must_match_projection_repository_basename(self):
        issue = {
            **issue_payload()[0],
            "title": "[REPO] other-repo",
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + projection_transport(),
        }

        with self.assertRaisesRegex(ValueError, "title|identity|repository"):
            parse_control_issues([issue], now=1791097200.0)

    def test_outsider_forged_projection_does_not_gain_control_trust(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "outside-user"},
            "body": ISSUE_BODY + projection_transport(),
        }

        self.assertEqual(parse_control_issues([issue]), {})

    def test_bot_control_without_projection_remains_rejected(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
        }

        self.assertEqual(parse_control_issues([issue]), {})

    def test_bot_control_with_stale_projection_fails_closed(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + projection_transport(
                generated_at="2026-10-03T05:50:00Z",
                valid_until="2026-10-04T05:50:00Z",
            ),
        }

        with self.assertRaisesRegex(ValueError, "stale"):
            parse_control_issues([issue], now=1791097200.0)

    def test_bot_control_with_mismatched_generation_id_fails_closed(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + projection_transport(corrupt_generation=True),
        }

        with self.assertRaisesRegex(ValueError, "generation_id"):
            parse_control_issues([issue], now=1791097200.0)

    def test_bot_control_with_noncanonical_validity_window_fails_closed(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + projection_transport(
                valid_until="2026-10-06T05:50:00Z",
            ),
        }

        with self.assertRaisesRegex(ValueError, "validity window"):
            parse_control_issues([issue], now=1791097200.0)

    def test_bot_control_with_future_generation_fails_closed(self):
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + projection_transport(
                generated_at="2026-10-05T05:50:00Z",
                valid_until="2026-10-06T05:50:00Z",
            ),
        }

        with self.assertRaisesRegex(ValueError, "future|not yet"):
            parse_control_issues([issue], now=1791097200.0)

    def test_bot_control_with_duplicate_projection_marker_fails_closed(self):
        block = projection_transport()
        issue = {
            **issue_payload()[0],
            "author_association": "NONE",
            "user": {"login": "github-actions[bot]"},
            "body": ISSUE_BODY + block + block,
        }

        with self.assertRaisesRegex(ValueError, "marker pair"):
            parse_control_issues([issue])

    def test_provider_preserves_last_good_when_derived_projection_stales(self):
        calls = [0]
        now = [1791094800.0]

        def fetcher():
            calls[0] += 1
            generated_at, valid_until = (
                ("2026-10-04T05:50:00Z", "2026-10-05T05:50:00Z")
                if calls[0] == 1
                else ("2026-10-03T05:50:00Z", "2026-10-04T05:50:00Z")
            )
            return [
                {
                    **issue_payload()[0],
                    "author_association": "NONE",
                    "user": {"login": "github-actions[bot]"},
                    "body": ISSUE_BODY + projection_transport(
                        generated_at=generated_at,
                        valid_until=valid_until,
                    ),
                }
            ]

        provider = DevflowStateProvider(
            fetcher=fetcher,
            clock=lambda: now[0],
            ttl_seconds=120.0,
            retry_seconds=30.0,
        )
        first = provider.snapshot()
        self.assertIn("example-repo", first.repositories)
        self.assertFalse(first.stale)

        now[0] += 121.0
        failed = provider.snapshot()

        self.assertTrue(failed.stale)
        self.assertIn("stale", failed.error)
        self.assertEqual(failed.repositories, first.repositories)

    def test_parse_control_issues_rejects_duplicate_trusted_controls(self):
        trusted = issue_payload()[0]
        duplicate = {
            **trusted,
            "number": 99,
            "html_url": "https://github.com/kinoko34077/devflow/issues/99",
        }

        with self.assertRaisesRegex(ValueError, "duplicate trusted Repository Control"):
            parse_control_issues([trusted, duplicate])

    def test_body_audit_freshness_is_ignored_in_favor_of_machine_projection_label(self):
        issue = issue_payload()[0]
        issue["body"] = ISSUE_BODY + "\n## Audit Freshness\n\n`DRIFTED`\n"
        issue["labels"] = [{"name": "devflow:audit-freshness:current"}]

        states = parse_control_issues([issue])

        self.assertEqual(states["example-repo"].audit_freshness, "CURRENT")

    def test_missing_projection_label_does_not_rederive_freshness(self):
        issue = issue_payload()[0]
        issue["labels"] = []

        states = parse_control_issues([issue])

        self.assertEqual(states["example-repo"].audit_freshness, "")

    def test_conflicting_projection_labels_fail_closed(self):
        issue = issue_payload()[0]
        issue["labels"] = [
            {"name": "devflow:audit-freshness:current"},
            {"name": "devflow:audit-freshness:drifted"},
        ]

        with self.assertRaisesRegex(ValueError, "conflicting Audit Freshness projection"):
            parse_control_issues([issue])

    def test_unrelated_labels_do_not_affect_projection(self):
        issue = issue_payload()[0]
        issue["labels"] = [
            {"name": "bug"},
            {"name": "devflow:audit-freshness:unknown"},
            {"name": "priority:p2"},
        ]

        states = parse_control_issues([issue])

        self.assertEqual(states["example-repo"].audit_freshness, "UNKNOWN")

    def test_provider_preserves_last_good_state_when_projection_conflicts(self):
        calls = [0]
        now = [1000.0]

        def fetcher():
            calls[0] += 1
            issue = issue_payload()[0]
            if calls[0] == 1:
                return [issue]
            issue["labels"] = [
                {"name": "devflow:audit-freshness:current"},
                {"name": "devflow:audit-freshness:unknown"},
            ]
            return [issue]

        provider = DevflowStateProvider(
            fetcher=fetcher,
            clock=lambda: now[0],
            ttl_seconds=120.0,
            retry_seconds=30.0,
        )
        first = provider.snapshot()
        self.assertEqual(first.repositories["example-repo"].audit_freshness, "CURRENT")

        now[0] += 121.0
        failed = provider.snapshot()

        self.assertTrue(failed.stale)
        self.assertIn("conflicting Audit Freshness projection", failed.error)
        self.assertEqual(failed.repositories["example-repo"].audit_freshness, "CURRENT")

    def test_provider_caches_one_public_issue_fetch_until_ttl_expires(self):
        calls = []
        now = [1000.0]

        def fetcher():
            calls.append(now[0])
            return issue_payload()

        provider = DevflowStateProvider(fetcher=fetcher, clock=lambda: now[0], ttl_seconds=120.0)

        first = provider.snapshot()
        second = provider.snapshot()
        now[0] += 119.0
        third = provider.snapshot()

        self.assertEqual(len(calls), 1)
        self.assertFalse(first.stale)
        self.assertEqual(first.repositories["example-repo"].work_status, "IMPLEMENTING")
        self.assertEqual(second.repositories, first.repositories)
        self.assertEqual(third.repositories, first.repositories)

        now[0] += 2.0
        provider.snapshot()
        self.assertEqual(len(calls), 2)

    def test_provider_keeps_last_successful_state_when_refresh_fails(self):
        calls = [0]
        now = [1000.0]

        def fetcher():
            calls[0] += 1
            if calls[0] == 1:
                return issue_payload()
            raise OSError("network down")

        provider = DevflowStateProvider(fetcher=fetcher, clock=lambda: now[0], ttl_seconds=120.0, retry_seconds=30.0)
        provider.snapshot()
        now[0] += 121.0

        failed = provider.snapshot()
        immediate_retry = provider.snapshot()

        self.assertTrue(failed.stale)
        self.assertIn("network down", failed.error)
        self.assertIn("example-repo", failed.repositories)
        self.assertEqual(immediate_retry.repositories, failed.repositories)
        self.assertEqual(calls[0], 2)

    def test_public_issue_fetch_uses_canonical_numbered_pages_not_link_header(self):
        class FakeResponse:
            def __init__(self, payload, link=""):
                self.payload = payload
                self.headers = {"Link": link}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        hostile_link = '<https://evil.example.invalid/steal?token=test>; rel="next"'
        first_page = [
            {**issue_payload()[0], "number": 1000 + n}
            for n in range(100)
        ]
        last_page = [{**issue_payload()[0], "number": 60}]
        responses = [
            FakeResponse(first_page, hostile_link),
            FakeResponse(last_page, hostile_link),
            FakeResponse(first_page, hostile_link),
            FakeResponse(last_page, hostile_link),
        ]
        requests = []
        def fake_open(request, timeout=3.0):
            requests.append(request)
            return responses.pop(0)

        with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": "fake-test-token"}):
            with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
                issues = _fetch_public_issues()

        self.assertEqual([item["number"] for item in issues], [
            *range(1000, 1100), 60,
        ])
        self.assertEqual([r.full_url for r in requests], [
            "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=1",
            "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=2",
            "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=1",
            "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=2",
        ])
        self.assertTrue(all(r.host == "api.github.com" for r in requests))
        self.assertTrue(all(r.get_header("Authorization") == "Bearer fake-test-token" for r in requests))
        self.assertTrue(all("evil.example" not in r.full_url for r in requests))

    def test_public_issue_fetch_stops_on_short_page_ignoring_untrusted_link(self):
        class FakeResponse:
            headers = {"Link": '<https://evil.example.invalid/leak>; rel="next"'}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(issue_payload()).encode("utf-8")

        requests = []
        def fake_open(request, timeout=3.0):
            requests.append(request.full_url)
            return FakeResponse()
        with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
            issues = _fetch_public_issues()
        self.assertEqual(issues, issue_payload())
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0].endswith("page=1"))

    def test_public_issue_fetch_rejects_missing_control_on_page_boundary_close(self):
        class FakeResponse:
            headers = {}
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        # A close between page 1 and page 2 shifts ID 50 to page 1.
        # The initial walk returns 101 items; the stable next walk returns 100.
        base = [{**issue_payload()[0], "number": n} for n in range(101, 201)]
        shifted = base[1:] + [{**issue_payload()[0], "number": 50}]
        responses = iter([
            FakeResponse(base), FakeResponse([{**issue_payload()[0], "number": 50}]),
            FakeResponse(shifted), FakeResponse([]),
        ])
        requests = []
        def fake_open(request, timeout=3.0):
            requests.append(request.full_url)
            return next(responses)

        with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
            with self.assertRaisesRegex(ValueError, "changed during pagination"):
                _fetch_public_issues()
        self.assertEqual(len(requests), 4)

    def test_public_issue_fetch_rejects_open_issue_during_page_boundary(self):
        class FakeResponse:
            headers = {}
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        first = [{**issue_payload()[0], "number": n} for n in range(1000, 1100)]
        last = [{**issue_payload()[0], "number": 1}]
        new = {**issue_payload()[0], "number": 2000}
        responses = iter([
            FakeResponse(first), FakeResponse(last),
            FakeResponse([new, *first[:99]]), FakeResponse([first[99], *last]),
        ])
        with patch("repo_monitor.devflow_state.urlopen", side_effect=lambda *a, **k: next(responses)):
            with self.assertRaisesRegex(ValueError, "changed during pagination"):
                _fetch_public_issues()

    def test_public_issue_fetch_rejects_duplicate_identity_across_pages(self):
        class FakeResponse:
            headers = {}
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        first = [{**issue_payload()[0], "number": n} for n in range(1000, 1100)]
        responses = iter([FakeResponse(first), FakeResponse([first[5]])])
        with patch("repo_monitor.devflow_state.urlopen", side_effect=lambda *a, **k: next(responses)):
            with self.assertRaisesRegex(ValueError, "duplicate devflow Issue identity"):
                _fetch_public_issues()

    def test_public_issue_fetch_rejects_failed_or_malformed_second_page(self):
        class FakeResponse:
            headers = {}
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        first = [{**issue_payload()[0], "number": n} for n in range(1000, 1100)]
        for bad in ("not-list", "http-error"):
            with self.subTest(bad=bad):
                requests = []
                def fake_open(request, timeout=3.0):
                    requests.append(request.full_url)
                    if len(requests) == 1:
                        return FakeResponse(first)
                    if bad == "http-error":
                        raise HTTPError(request.full_url, 502, "upstream error", {}, None)
                    return FakeResponse({"error": "not an Issues list"})
                with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
                    with self.assertRaises((ValueError, HTTPError)):
                        _fetch_public_issues()
                self.assertEqual(len(requests), 2)

    def test_public_issue_fetch_rejects_full_twentieth_page_not_partial(self):
        class FakeResponse:
            headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps([issue_payload()[0]] * 100).encode("utf-8")

        requests = []
        def fake_open(request, timeout=3.0):
            requests.append(request.full_url)
            return FakeResponse()
        with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
            with self.assertRaisesRegex(ValueError, "excessive devflow Issues pagination"):
                _fetch_public_issues()
        self.assertEqual(len(requests), 20)
        self.assertTrue(requests[0].endswith("page=1"))
        self.assertTrue(requests[-1].endswith("page=20"))

    def test_public_issue_fetch_rejects_oversized_response_page(self):
        class FakeResponse:
            headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps([issue_payload()[0]] * 101).encode("utf-8")
        with patch("repo_monitor.devflow_state.urlopen", return_value=FakeResponse()):
            with self.assertRaisesRegex(ValueError, "unexpected devflow Issues page size"):
                _fetch_public_issues()

    def test_authenticated_redirect_is_refused_at_transport_boundary(self):
        # Standard urllib redirects retain the original Authorization header.
        # The public devflow API reader must refuse ANY redirect, including
        # redirects to an external host, before another request can be made.
        from urllib.request import Request
        from repo_monitor.devflow_state import _RejectIssuesRedirect, urlopen

        request = Request(
            "https://api.github.com/repositories/1385584542/issues"
            "?state=open&per_page=100&page=2",
            headers={"Authorization": "Bearer fake-test-token"},
        )
        with self.assertRaisesRegex(HTTPError, "devflow Issues redirect refused"):
            _RejectIssuesRedirect().redirect_request(
                request, None, 302, "Found", {},
                "https://redirect.example.invalid/capture",
            )

        class NoNetworkOpener:
            def open(self, value, timeout=0):
                self.last_request = value
                self.timeout = timeout
                raise RuntimeError("no network expected")

        opener = NoNetworkOpener()
        with patch("repo_monitor.devflow_state.build_opener", return_value=opener) as patched:
            with self.assertRaisesRegex(RuntimeError, "no network expected"):
                urlopen(request, timeout=3.0)
            self.assertIsInstance(patched.call_args.args[0], _RejectIssuesRedirect)
        self.assertIs(opener.last_request, request)
        self.assertEqual(opener.timeout, 3.0)

    def test_public_issue_fetch_uses_explicit_actions_token_only_for_devflow(self):
        class FakeResponse:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"[]"

        requests = []

        def fake_urlopen(request, timeout=3.0):
            requests.append(request)
            return FakeResponse()

        with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": "test-ephemeral-token"}):
            with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_urlopen):
                self.assertEqual(_fetch_public_issues(), [])
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer test-ephemeral-token")
        self.assertEqual(requests[0].host, "api.github.com")
        self.assertNotIn("test-ephemeral-token", requests[0].full_url)

    def test_public_issue_fetch_never_uses_untrusted_next_url(self):
        class FakeResponse:
            def __init__(self, link):
                self.headers = {"Link": f'<{link}>; rel="next"'}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b"[]"

        disallowed = [
            "https://evil.example.invalid/steal",
            "http://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=2",
            "https://api.github.com/repos/kinoko34077/private/issues?state=open&per_page=100&page=2",
            "https://api.github.com/repos/kinoko34077/devflow/issues?state=closed&per_page=100&page=2",
            "https://api.github.com/repositories/9999999999/issues?after=not-trusted",
            "https://api.github.com/repositories/1385584542/issues?after=Y3Vyc29yOnYyOkIw",
        ]
        for link in disallowed:
            with self.subTest(link=link):
                requests = []
                def fake_open(request, timeout=3.0):
                    requests.append(request.full_url)
                    return FakeResponse(link)
                with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": "fake-test-secret"}):
                    with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
                        self.assertEqual(_fetch_public_issues(), [])
                self.assertEqual(len(requests), 1)
                self.assertEqual(
                    requests[0],
                    "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=1",
                )
                self.assertNotIn("fake-test-secret", requests[0])

    def test_public_issue_fetch_remains_anonymous_without_workflow_token(self):
        class FakeResponse:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"[]"

        requested = []

        def fake_urlopen(request, timeout=3.0):
            requested.append(request)
            return FakeResponse()

        with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": ""}):
            with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_urlopen):
                _fetch_public_issues()
        self.assertIsNone(requested[0].get_header("Authorization"))

    def test_public_fetcher_default_ttl_budgets_anonymous_requests(self):
        class FakeResponse:
            headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b"[]"

        now = [1000.0]
        calls = []
        def fake_open(request, timeout=3.0):
            calls.append(request)
            return FakeResponse()

        with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": ""}):
            with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
                provider = DevflowStateProvider(clock=lambda: now[0])
                self.assertEqual(provider._ttl_seconds, 600.0)
                provider.snapshot()
                self.assertEqual(len(calls), 1)
                for moment in (1120.0, 1300.0, 1599.0):
                    now[0] = moment
                    provider.snapshot()
                self.assertEqual(len(calls), 1)
                now[0] = 1600.0
                provider.snapshot()
                self.assertEqual(len(calls), 2)

    def test_public_fetcher_default_ttl_keeps_authenticated_or_explicit_refresh(self):
        now = [1000.0]
        with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": "ephemeral"}):
            token_provider = DevflowStateProvider(clock=lambda: now[0])
            self.assertEqual(token_provider._ttl_seconds, 120.0)
        with patch.dict(os.environ, {"REPO_MONITOR_PUBLIC_READ_TOKEN": ""}):
            explicit_provider = DevflowStateProvider(clock=lambda: now[0], ttl_seconds=120.0)
            self.assertEqual(explicit_provider._ttl_seconds, 120.0)
        # A custom fetcher is not necessarily backed by the GitHub rate limit.
        custom_provider = DevflowStateProvider(fetcher=lambda: [], clock=lambda: now[0])
        self.assertEqual(custom_provider._ttl_seconds, 120.0)

    def test_public_issue_fetch_rejects_second_walk_downstream_errors(self):
        class FakeResponse:
            headers = {}
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        first = [{**issue_payload()[0], "number": n} for n in range(1000, 1100)]
        last = [{**issue_payload()[0], "number": 11}]
        for kind in ("http-error", "non-list", "non-mapping"):
            with self.subTest(kind=kind):
                requests = []
                def fake_open(request, timeout=3.0):
                    requests.append(request.full_url)
                    if len(requests) in (1, 3):
                        return FakeResponse(first)
                    if len(requests) == 2:
                        return FakeResponse(last)
                    if kind == "http-error":
                        raise HTTPError(request.full_url, 502, "failed page", {}, None)
                    if kind == "non-list":
                        return FakeResponse({"error": "bad second walk"})
                    return FakeResponse(["invalid record"])
                with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_open):
                    with self.assertRaises((HTTPError, ValueError)):
                        _fetch_public_issues()
                self.assertEqual([u.rsplit("=", 1)[-1] for u in requests], ["1", "2", "1", "2"])

    def test_provider_honors_rate_limit_reset_before_retrying(self):
        calls = [0]
        now = [1000.0]
        headers = Message()
        headers["X-RateLimit-Reset"] = "1100"

        def fetcher():
            calls[0] += 1
            raise HTTPError("https://api.github.com/", 429, "rate limited", headers, None)

        provider = DevflowStateProvider(fetcher=fetcher, clock=lambda: now[0], retry_seconds=30.0)
        provider.snapshot()
        now[0] = 1031.0
        provider.snapshot()
        self.assertEqual(calls[0], 1)
        now[0] = 1100.0
        provider.snapshot()
        self.assertEqual(calls[0], 2)

    def test_nonblocking_snapshot_refreshes_in_background_without_duplicate_fetches(self):
        started = threading.Event()
        release = threading.Event()
        calls = [0]

        def fetcher():
            calls[0] += 1
            started.set()
            release.wait(timeout=2.0)
            return issue_payload()

        provider = DevflowStateProvider(fetcher=fetcher, ttl_seconds=120.0)

        initial = provider.snapshot_nonblocking()
        self.assertEqual(initial.repositories, {})
        self.assertTrue(started.wait(timeout=0.5))

        while_running = provider.snapshot_nonblocking()
        self.assertEqual(while_running.repositories, {})
        self.assertEqual(calls[0], 1)

        release.set()
        deadline = time.monotonic() + 1.0
        completed = provider.snapshot_nonblocking()
        while "example-repo" not in completed.repositories and time.monotonic() < deadline:
            time.sleep(0.01)
            completed = provider.snapshot_nonblocking()

        self.assertIn("example-repo", completed.repositories)
        self.assertEqual(calls[0], 1)


if __name__ == "__main__":
    unittest.main()
