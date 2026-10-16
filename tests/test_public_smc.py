"""Public SMC projection must reject forged/partial reports and omit raw provenance."""
import importlib.util
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "build_public_smc.py"
spec = importlib.util.spec_from_file_location("build_public_smc", SCRIPT)
smc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smc)

REPOS = [
    ("kinoko34077/devflow", 367),
    ("kinoko34077/execution-coordinator", 127),
    ("kinoko34077/kinotch-repository-base", 50),
]


def sample():
    rows = [{
        "repository": repo,
        "slot_id": "common.correctness",
        "scope_kind": "repository",
        "scope_selector": ".",
        "lens": "correctness", "depth": "STANDARD",
        "status": "NOT_RUN", "reason": "not run",
        "evidence_url": "https://github.com/example/untrusted",
        "run_id": "private", "current_fingerprint": "sha256:secret",
    } for repo, _ in REPOS]
    return {
        "schema_version": "smc-coverage-report.v1",
        "repository_count": 3, "row_count": 3,
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"),
        "coverage_state_counts": {"NOT_RUN": 3},
        "repositories": [{
            "repository": repo, "ledger_issue_number": issue,
            "slot_depth_rows": 1, "coverage_states": {"NOT_RUN": 1},
        } for repo, issue in REPOS],
        "rows": rows,
    }


class PublicSmcTests(unittest.TestCase):
    def test_exact_three_pilot_summary_and_no_raw_exposure(self):
        out = smc.public_projection(sample())
        self.assertEqual(3, out["repository_count"])
        self.assertEqual(3, out["row_count"])
        self.assertEqual(["NOT_RUN"] * 3, [r["status"] for r in out["rows"]])
        text = json.dumps(out)
        for forbidden in ("sha256:secret", "private", "untrusted", "run_id", "current_fingerprint", "comments_scanned"):
            self.assertNotIn(forbidden, text)

    def test_rejects_foreign_ledger_and_forged_status(self):
        for mutate in (
            lambda x: x["repositories"][0].update(ledger_issue_number=999),
            lambda x: x["rows"][0].update(status="VERIFIED"),
            lambda x: x["rows"][0].update(repository="kinoko34077/unknown"),
            lambda x: x.update(row_count=8),
            lambda x: x["coverage_state_counts"].update(NOT_RUN=8),
            lambda x: x["rows"].append(dict(x["rows"][0])),
            lambda x: x.update(observed_at="not-a-date"),
        ):
            data = sample()
            mutate(data)
            with self.subTest(mutator=mutate), self.assertRaises(ValueError):
                smc.public_projection(data)

    def test_noncompletion_states_are_retained(self):
        data = sample()
        data["rows"][0]["status"] = "SOURCE_DRIFT"
        data["repositories"][0]["coverage_states"] = {"SOURCE_DRIFT": 1}
        data["coverage_state_counts"] = {"NOT_RUN": 2, "SOURCE_DRIFT": 1}
        out = smc.public_projection(data)
        self.assertEqual(1, out["coverage_state_counts"] if "coverage_state_counts" in out else
                         sum(r["status"] == "SOURCE_DRIFT" for r in out["rows"]))

    def test_html_relabels_local_only_renderer_and_preserves_warnings(self):
        projection = smc.public_projection(sample())
        local = ('<h1>SMC 多角的監査カバレッジ</h1>'
                 '<p>ATTESTED_SCOPE_MATCH</p>'
                 '<footer>ローカル表示。外部送信・永続保存・監査実行・GitHubへの書込みは行いません。</footer>')
        html = smc.render_public_html(projection, lambda _: local)
        self.assertIn(projection["observed_at"], html)
        self.assertIn("公開GitHub Pages", html)
        self.assertIn("ATTESTED_SCOPE_MATCH", html)
        self.assertNotIn("ローカル表示。", html)


if __name__ == "__main__":
    unittest.main()
