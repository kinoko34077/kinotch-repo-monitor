from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / ".github" / "workflows" / "verify.yml"


class VerifyWorkflowContractTests(unittest.TestCase):
    def test_external_actions_are_immutable_sha_pinned(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")
        refs = re.findall(r"(?m)^\s*- uses:\s*([^\s#]+)", text)
        self.assertGreaterEqual(len(refs), 3)
        for ref in refs:
            with self.subTest(ref=ref):
                self.assertRegex(ref, r"^[^@\s]+@[0-9a-f]{40}$")

    def test_workflow_declares_read_only_contents_permission(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"(?ms)^permissions:\s*\n\s+contents:\s+read\s*$",
        )


if __name__ == "__main__":
    unittest.main()
