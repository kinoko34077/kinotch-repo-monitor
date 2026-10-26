"""Offline regression coverage for devflow principal contract drift detector."""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from tools import check_devflow_principals as checker


def canonical(mapping: str = '{79015263: "kinoko34077"}') -> str:
    return "from types import MappingProxyType\nTRUSTED_PRINCIPAL_IDS = MappingProxyType(" + mapping + ")\n"


class _Response:
    def __init__(self, text: str):
        self.payload = text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class PrincipalContractTests(unittest.TestCase):
    def test_parse_canonical_without_executing_code(self):
        self.assertEqual(checker.parse_principals(canonical()), {79015263: "kinoko34077"})

    def test_invalid_canonical_fails_closed(self):
        for source in (
            "TRUSTED_PRINCIPAL_IDS = {}", canonical("{}"),
            canonical('{"79015263": "kinoko34077"}'), canonical('{True: "kinoko34077"}'),
            canonical("{79015263: ''}"), "TRUSTED_PRINCIPAL_IDS = open('/tmp/x')",
        ):
            with self.subTest(source=source):
                with self.assertRaises((ValueError, SyntaxError)):
                    checker.parse_principals(source)

    def test_main_accepts_match_but_rejects_drift_and_fetch_failure(self):
        for source, expected_status, expected_code in (
            (canonical(), "MATCH", 0),
            (canonical('{79015264: "other"}'), "DRIFT", 1),
            ("TRUSTED_PRINCIPAL_IDS = {}", "UNKNOWN", 1),
        ):
            with self.subTest(expected_status=expected_status), patch.object(
                checker.urllib.request, "urlopen", return_value=_Response(source)
            ), contextlib.redirect_stdout(io.StringIO()) as out:
                result = checker.main()
                self.assertEqual(result, expected_code)
                self.assertIn(expected_status, out.getvalue())
        with patch.object(checker.urllib.request, "urlopen", side_effect=OSError("offline")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(checker.main(), 1)
            self.assertIn("UNKNOWN", out.getvalue())


if __name__ == "__main__":
    unittest.main()
