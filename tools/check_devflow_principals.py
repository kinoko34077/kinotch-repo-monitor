"""Fail-closed build-time verification of the devflow-owned principal mapping."""
import ast
import json
import urllib.request

from repo_monitor.devflow_state import TRUSTED_CONTROL_PRINCIPALS

SOURCE = "https://raw.githubusercontent.com/kinoko34077/devflow/main/tools/github_issue_trust.py"


def parse_principals(source: str) -> dict[int, str]:
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "TRUSTED_PRINCIPAL_IDS" for t in node.targets):
            continue
        v = node.value
        if not (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                and v.func.id == "MappingProxyType" and len(v.args) == 1):
            break
        result = ast.literal_eval(v.args[0])
        if isinstance(result, dict) and result and all(
            type(k) is int and k > 0 and isinstance(v, str) and bool(v)
            for k, v in result.items()
        ):
            return result
    raise ValueError("Unrecognized canonical principal format")


def main() -> int:
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "repo-monitor-trust-contract"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            canonical = parse_principals(response.read().decode("utf-8"))
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print(json.dumps({"status": "UNKNOWN", "reason": type(exc).__name__}))
        return 1
    same = canonical == dict(TRUSTED_CONTROL_PRINCIPALS)
    print(json.dumps({"status": "MATCH" if same else "DRIFT"}))
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
