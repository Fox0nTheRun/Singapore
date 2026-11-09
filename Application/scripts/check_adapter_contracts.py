"""Person D's read-only static audit of B/C Python adapter signatures.

This does NOT import DB drivers, connect to a server, or establish runtime health.
Run from project root: python scripts/check_adapter_contracts.py
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "src/hdb_insights/db/mariadb_repository.py"
C = ROOT / "src/hdb_insights/db/mongodb_adapter.py"
OPERATIONS = {
    "search_resale": ["filters", "limit", "offset"],
    "summarise_resale": ["filters"],
    "resale_trend": ["filters"],
    "demographic_profile": ["group_type", "group_code", "survey_year"],
    "mobility_breakdown": ["workplace_area", "residence_region_code", "survey_year"],
    "list_filter_options": ["domain"],
    "create_demo_resale": ["payload"],
    "get_demo_resale": ["demo_record_id"],
    "update_demo_resale": ["demo_record_id", "changes"],
    "delete_demo_resale": ["demo_record_id"],
}


def methods(path: Path, cls: str | None = None):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if cls is not None:
        parent = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls), None)
        if parent is None:
            raise ValueError(f"Missing class {cls} in {path.name}")
    else:
        parent = tree
    return {node.name: node for node in parent.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def check():
    a, b = methods(B), methods(C, "MongoDBAdapter")
    failures = []
    for method, args in OPERATIONS.items():
        for side, source, prefix in (("MariaDB", a, []), ("MongoDB", b, ["self", "active"])):
            function = source.get(method)
            found = [item.arg for item in function.args.args] if function is not None else None
            expected = prefix + args
            if found != expected:
                failures.append({"backend": side, "operation": method, "expected": expected, "found": found})
    init = b.get("__init__")
    kwonly = [item.arg for item in init.args.kwonlyargs] if init else []
    if "options_formatter" not in kwonly or "missing_mobility_policy" not in kwonly:
        failures.append({"backend": "MongoDB", "operation": "__init__", "error": "Missing configuration dependency"})
    return {"status": "PASS" if not failures else "FAIL", "method_count": len(OPERATIONS),
            "method_pairs_checked": 2 * len(OPERATIONS), "source_files": [str(B.relative_to(ROOT)), str(C.relative_to(ROOT))],
            "verification_type": "static AST signatures only; database execution not tested", "failures": failures}


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
