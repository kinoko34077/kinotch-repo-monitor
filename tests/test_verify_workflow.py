from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFY_WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


class VerifyWorkflowSupplyChainTests(unittest.TestCase):
    def test_external_actions_are_immutable_sha_pinned(self) -> None:
        workflow = VERIFY_WORKFLOW.read_text(encoding="utf-8")
        refs = re.findall(r"^\s*-\s+uses:\s+([^@\s]+)@([^\s#]+)", workflow, flags=re.MULTILINE)
        self.assertTrue(refs, "verify workflow must contain external Action uses")
        for action, ref in refs:
            with self.subTest(action=action, ref=ref):
                self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_workflow_declares_read_only_contents_permission(self) -> None:
        workflow = VERIFY_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(
            workflow,
            r"(?ms)^permissions:\s*\n\s+contents:\s+read\s*$",
        )


if __name__ == "__main__":
    unittest.main()
