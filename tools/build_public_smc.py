"""Public SMC Pages projection from the accepted devflow GET-only report.

No GitHub network, credential management, claim admission, ledger mutation, or
private source data. The caller gives the upstream CLI's freshly generated JSON.
This module narrows the projection before passing it to the upstream renderer.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "smc-coverage-report.v1"
ACCEPTED = {
    "kinoko34077/devflow": 367,
    "kinoko34077/execution-coordinator": 127,
    "kinoko34077/kinotch-repository-base": 50,
}
STATUSES = frozenset({
    "NOT_RUN", "NO_COVERAGE", "SOURCE_DRIFT", "UNKNOWN_FINGERPRINT",
    "CATALOG_DRIFT", "LENS_DRIFT", "SCOPE_DRIFT", "UNTRUSTED",
    "AMBIGUOUS_HISTORY", "INSUFFICIENT_EVIDENCE",
    "LEGACY_SCOPE_UNBOUND", "ATTESTED_SCOPE_MATCH",
})
DEPTHS = frozenset({"CONTROL", "STANDARD", "DEEP"})
SOURCE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def public_projection(report: dict) -> dict:
    """Fail closed unless every published row belongs to the 3 public PILOTs."""
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA:
        raise ValueError("unsupported canonical report")
    repos = report.get("repositories")
    rows = report.get("rows")
    if not isinstance(repos, list) or len(repos) != 3 or not isinstance(rows, list):
        raise ValueError("missing exact three-pilot report")
    if len(rows) < 1 or len(rows) > 1500 or report.get("repository_count") != 3 or report.get("row_count") != len(rows):
        raise ValueError("report cardinality mismatch")
    observed_at = report.get("observed_at")
    if not isinstance(observed_at, str) or not SOURCE_RE.fullmatch(observed_at):
        raise ValueError("missing canonical source observation time")
    timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if timestamp > datetime.now(timezone.utc):
        raise ValueError("future source observation")
    by_repo: dict[str, dict] = {}
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError("bad repository summary")
        name = repo.get("repository")
        if name not in ACCEPTED or repo.get("ledger_issue_number") != ACCEPTED[name] or name in by_repo:
            raise ValueError("unapproved repository or Ledger")
        by_repo[name] = repo
    if len(by_repo) != 3:
        raise ValueError("missing accepted pilot")
    counts: Counter[str] = Counter()
    repo_counts: dict[str, Counter[str]] = {name: Counter() for name in ACCEPTED}
    ids: set[tuple[str, str, str]] = set()
    safe_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid coverage row")
        name, status, depth = row.get("repository"), row.get("status"), row.get("depth")
        if name not in by_repo or status not in STATUSES or depth not in DEPTHS:
            raise ValueError("untrusted source/depth/status")
        for key in ("slot_id", "scope_kind", "scope_selector", "lens", "reason"):
            value = row.get(key)
            if not isinstance(value, str) or len(value) > 240 or (key != "reason" and not value):
                raise ValueError("untrusted slot text")
        identity = (name, row["slot_id"], depth)
        if identity in ids:
            raise ValueError("duplicate source slot")
        ids.add(identity)
        counts[status] += 1
        repo_counts[name][status] += 1
        safe_rows.append({
            "repository": name, "scope_kind": row["scope_kind"],
            "scope_selector": row["scope_selector"], "lens": row["lens"],
            "depth": depth, "status": status, "reason": row["reason"],
            "completed_at": row.get("completed_at")
                if isinstance(row.get("completed_at"), str) and len(row["completed_at"]) <= 35 else None,
            "evidence_url": None,
        })
    if dict(counts) != report.get("coverage_state_counts"):
        raise ValueError("global coverage state mismatch")
    public_repos = []
    for name in sorted(ACCEPTED):
        original = by_repo[name]
        if original.get("slot_depth_rows") != sum(repo_counts[name].values()) \
                or original.get("coverage_states") != dict(repo_counts[name]):
            raise ValueError("repository coverage counts mismatch")
        noncredit_record_count = original.get("noncredit_record_count")
        if type(noncredit_record_count) is not int or noncredit_record_count < 0:
            raise ValueError("invalid noncredit_record_count")
        public_repos.append({
            "repository": name, "ledger_issue_number": ACCEPTED[name],
            "slot_depth_rows": original["slot_depth_rows"],
            "noncredit_record_count": noncredit_record_count,
            "coverage_states": dict(sorted(repo_counts[name].items())),
        })
    return {
        "schema_version": SCHEMA,
        "repository_count": 3,
        "row_count": len(safe_rows),
        "repositories": public_repos,
        "rows": safe_rows,
        "limits": [
            "公開時刻のスナップショットです。GitHubの現在状態を表示するものではありません。",
            "ATTESTED_SCOPE_MATCH は記録の対応のみで、独立した実監査の完了証明ではありません。",
            "NO_COVERAGE / SOURCE_DRIFT / UNKNOWN_FINGERPRINT は状態を隠さず表示します。",
            "掲載対象は公開されている既存3 PILOTのみ。元コメント、トークン、ファイルパス、実行IDは公開しません。",
        ],
        "observed_at": observed_at,
    }


def render_public_html(projection: dict, renderer) -> str:
    html = renderer(projection)
    anchor = '<h1>SMC 多角的監査カバレッジ</h1>'
    footer = '<footer>ローカル表示。外部送信・永続保存・監査実行・GitHubへの書込みは行いません。</footer>'
    if html.count(anchor) != 1 or html.count(footer) != 1:
        raise ValueError("upstream renderer shape drift")
    observed = projection["observed_at"]
    html = html.replace(anchor, anchor + '<p class="hint">公開GitHub Pagesの読取専用スナップショット。元Ledger観測: '
        + observed + '。次回更新まで変化は反映されません。</p>')
    html = html.replace(footer, '<footer>公開済みの派生スナップショット。'
        '監査の実行・受入・権限付与・GitHubへの書込みは行いません。</footer>')
    return html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    opts = parser.parse_args()
    raw = opts.report.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("report exceeds 1 MiB")
    projection = public_projection(json.loads(raw))
    upstream_path = opts.upstream.resolve(strict=True)
    sys.path.insert(0, str(upstream_path))
    upstream = importlib.import_module("tools.maintenance_coverage_html")
    result = render_public_html(projection, upstream.render_coverage_html)
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    opts.output.write_text(result, encoding="utf-8")
    print("SMC public snapshot accepted: 3 PILOTs, "
          + str(projection["row_count"]) + " rows, observed=" + projection["observed_at"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
