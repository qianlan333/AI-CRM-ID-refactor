from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "architecture" / "route_ownership_manifest.yml"
INVENTORY_DIR = ROOT / "docs" / "architecture"
REPORT_VERSION = "1"

ROUTE_REF_RE = re.compile(r"`(/[^`\s|]+)`")
TEST_REF_RE = re.compile(r"tests/[^`) ,|]+")


@dataclass(frozen=True)
class RouteInventoryRecord:
    path: str
    extracted_route_count: int
    exact_manifest_match_count: int
    wildcard_or_family_count: int
    test_reference_count: int
    classification: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "extracted_route_count": self.extracted_route_count,
            "exact_manifest_match_count": self.exact_manifest_match_count,
            "wildcard_or_family_count": self.wildcard_or_family_count,
            "test_reference_count": self.test_reference_count,
            "classification": self.classification,
            "reason": self.reason,
        }


def build_report(root: Path = ROOT, *, generated_at: str | None = None) -> dict[str, object]:
    root = root.resolve()
    manifest_paths = _manifest_paths(root / "docs" / "architecture" / "route_ownership_manifest.yml")
    records = [_inventory_record(path, root=root, manifest_paths=manifest_paths) for path in sorted((root / "docs" / "architecture").glob("*route_inventory.md"))]
    summary: dict[str, Any] = {
        "manifest_route_count": len(manifest_paths),
        "inventory_file_count": len(records),
        "classifications": {},
    }
    for record in records:
        summary["classifications"][record.classification] = summary["classifications"].get(record.classification, 0) + 1
    return {
        "version": REPORT_VERSION,
        "root": ".",
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "inventories": [record.as_dict() for record in records],
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    records = list(report["inventories"])
    lines = [
        "# Route Inventory Consolidation Inventory",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "This report is generated from `docs/architecture/route_ownership_manifest.yml`",
        "and `docs/architecture/*route_inventory.md` by",
        "`tools/report_route_inventory_consolidation.py`. It does not delete, move,",
        "or deprecate any route inventory file.",
        "",
        "## Current Sources",
        "",
        "- Canonical manifest: `docs/architecture/route_ownership_manifest.yml`",
        "- Manifest contract: `docs/architecture/route_ownership_manifest.md`",
        "- Manifest checker: `tools/check_route_ownership_manifest.py`",
        "- Manifest regression test: `tests/test_route_ownership_manifest.py`",
        "",
        f"The manifest currently covers {summary['manifest_route_count']} FastAPI routes.",
        f"The hand-written inventory set currently contains {summary['inventory_file_count']} `*_route_inventory.md` files.",
        "",
        "## Classification Summary",
        "",
    ]
    for classification, count in sorted(summary["classifications"].items()):
        lines.append(f"- `{classification}`: {count}")
    lines.extend(["", "## Inventory Details", ""])
    for classification in ("mostly_manifest_derivable", "retain_closeout_evidence", "needs_manual_review"):
        subset = [record for record in records if record["classification"] == classification]
        if not subset:
            continue
        lines.extend([f"### {classification}", "", "| Inventory | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |", "| --- | ---: | ---: | ---: | ---: | --- |"])
        for record in subset:
            lines.append(
                "| `{path}` | {routes} | {exact} | {wildcard} | {tests} | {reason} |".format(
                    path=record["path"],
                    routes=record["extracted_route_count"],
                    exact=record["exact_manifest_match_count"],
                    wildcard=record["wildcard_or_family_count"],
                    tests=record["test_reference_count"],
                    reason=record["reason"],
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Recommended Order",
            "",
            "1. Keep all existing route inventory tests in place.",
            "2. Use this report to compare generated route/method/owner rows against the",
            "   hand-written route inventory files.",
            "3. Archive only rows proven redundant; keep closeout evidence sections under",
            "   `docs/reports/evidence/` or a future `docs/archive/route_inventory/`.",
            "4. Only after a second PR proves parity, replace hand-written route tables with",
            "   generated output.",
            "",
            "## Non-Goals",
            "",
            "- Do not delete route inventory docs in this batch.",
            "- Do not delete `tests/test_*_route_inventory.py`.",
            "- Do not change route ownership manifest semantics.",
            "- Do not change FastAPI router registration or route behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report_files(report: dict[str, object], *, summary_output: Path | None = None, json_output: Path | None = None) -> None:
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(render_markdown(report), encoding="utf-8")
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report route inventory consolidation candidates without changing runtime.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-output")
    parser.add_argument("--summary-output")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = build_report(root)
    write_report_files(
        report,
        summary_output=(root / args.summary_output) if args.summary_output else None,
        json_output=(root / args.json_output) if args.json_output else None,
    )
    print(render_markdown(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _manifest_paths(path: Path) -> set[str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(route.get("path", "")) for route in raw.get("routes", []) if route.get("path")}


def _inventory_record(path: Path, *, root: Path, manifest_paths: set[str]) -> RouteInventoryRecord:
    text = path.read_text(encoding="utf-8")
    route_refs = sorted(set(ROUTE_REF_RE.findall(text)))
    exact_matches = [route for route in route_refs if route in manifest_paths]
    wildcard_refs = [route for route in route_refs if "*" in route or "{path:path}" in route or route.endswith("*")]
    test_refs = sorted(set(TEST_REF_RE.findall(text)))
    classification, reason = _classify(route_refs=route_refs, exact_matches=exact_matches, wildcard_refs=wildcard_refs, test_refs=test_refs)
    return RouteInventoryRecord(
        path=str(path.relative_to(root)),
        extracted_route_count=len(route_refs),
        exact_manifest_match_count=len(exact_matches),
        wildcard_or_family_count=len(wildcard_refs),
        test_reference_count=len(test_refs),
        classification=classification,
        reason=reason,
    )


def _classify(*, route_refs: list[str], exact_matches: list[str], wildcard_refs: list[str], test_refs: list[str]) -> tuple[str, str]:
    if not route_refs:
        return "needs_manual_review", "No route-like backtick paths were extracted."
    if wildcard_refs or len(exact_matches) < len(route_refs):
        return "retain_closeout_evidence", "Contains wildcard/family refs or route refs not exactly covered by the manifest."
    if test_refs:
        return "mostly_manifest_derivable", "Exact routes match manifest; preserve linked test evidence until a generated table proves parity."
    return "mostly_manifest_derivable", "Exact routes match manifest and can be compared with generated route rows."


if __name__ == "__main__":
    raise SystemExit(main())
