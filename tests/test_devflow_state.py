import json
import threading
import time
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from repo_monitor.devflow_state import DevflowStateProvider, _fetch_public_issues, parse_control_issues


ISSUE_BODY = """## Repository

`kinoko34077/example-repo`

## Work Status

`IMPLEMENTING`

## Type

`FEATURE`

## Repository State

`ACTIVE`

## Active Work

`example-repo#12` — implement the feature.

## Next Action

`VERIFY — run CI`
"""


def issue_payload():
    return [
        {
            "number": 59,
            "title": "[REPO] example-repo",
            "body": ISSUE_BODY,
            "html_url": "https://github.com/kinoko34077/devflow/issues/59",
            "updated_at": "2026-09-26T03:00:00Z",
            "author_association": "OWNER",
        }
    ]


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
        self.assertEqual(state.work_status, "IMPLEMENTING")
        self.assertEqual(state.repository_state, "ACTIVE")
        self.assertEqual(state.active_work, "example-repo#12 — implement the feature.")
        self.assertEqual(state.next_action, "VERIFY — run CI")
        self.assertEqual(state.issue_number, 59)
        self.assertEqual(state.issue_url, "https://github.com/kinoko34077/devflow/issues/59")
        self.assertEqual(state.updated_at, "2026-09-26T03:00:00Z")

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

    def test_parse_control_issues_rejects_duplicate_trusted_controls(self):
        trusted = issue_payload()[0]
        duplicate = {
            **trusted,
            "number": 99,
            "html_url": "https://github.com/kinoko34077/devflow/issues/99",
        }

        with self.assertRaisesRegex(ValueError, "duplicate trusted Repository Control"):
            parse_control_issues([trusted, duplicate])

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

    def test_public_issue_fetch_follows_github_next_links(self):
        class FakeResponse:
            def __init__(self, payload, link=""):
                self._payload = payload
                self.headers = {"Link": link}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(self._payload).encode("utf-8")

        next_url = "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100&page=2"
        responses = [
            FakeResponse([issue_payload()[0]], f'<{next_url}>; rel="next"'),
            FakeResponse([{**issue_payload()[0], "number": 60, "title": "[REPO] second-repo"}]),
        ]
        requested = []

        def fake_urlopen(request, timeout=3.0):
            requested.append(request.full_url)
            return responses.pop(0)

        with patch("repo_monitor.devflow_state.urlopen", side_effect=fake_urlopen):
            issues = _fetch_public_issues()

        self.assertEqual([item["number"] for item in issues], [59, 60])
        self.assertEqual(requested[1], next_url)

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
