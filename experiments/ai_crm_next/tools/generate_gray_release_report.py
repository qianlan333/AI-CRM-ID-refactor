#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Json = dict[str, Any]


def _load_json(path: str, *, label: str) -> Json:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"{label} JSON does not exist: {json_path}")
    with json_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} JSON must contain an object: {json_path}")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _side_effect_safety(*reports: Json) -> Json:
    safety: Json = {}
    for report in reports:
        source = report.get("side_effect_safety")
        if isinstance(source, dict):
            for key, value in source.items():
                safety[key] = value
    return safety


def _status_from_report(report: Json) -> str:
    if report.get("ok") is True or str(report.get("overall", "")).upper() == "PASS":
        return "PASS"
    if report.get("ok") is False or str(report.get("overall", "")).upper() == "FAIL":
        return "FAIL"
    return str(report.get("overall") or "UNKNOWN")


def build_report(batch: str, input_json: str, parity_json: str) -> Json:
    smoke = _load_json(input_json, label="smoke")
    parity = _load_json(parity_json, label="parity")

    blockers = _as_list(smoke.get("blockers")) + _as_list(parity.get("blockers"))
    warnings = _as_list(smoke.get("warnings")) + _as_list(parity.get("warnings"))
    skipped = _as_list(smoke.get("skipped")) + _as_list(parity.get("skipped"))
    side_effect_safety = _side_effect_safety(smoke, parity)
    source_status = {
        "smoke": _status_from_report(smoke),
        "parity": _status_from_report(parity),
    }
    go = not blockers and source_status["smoke"] != "FAIL" and source_status["parity"] != "FAIL"
    recommendation = "GO" if go else "NO_GO"

    return {
        "batch": batch,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_reports": {
            "smoke_json": str(input_json),
            "parity_json": str(parity_json),
        },
        "source_status": source_status,
        "blockers": blockers,
        "warnings": warnings,
        "skipped": skipped,
        "side_effect_safety": side_effect_safety,
        "go_no_go_recommendation": recommendation,
    }


def write_json_report(report: Json, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: Json, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Gray Release Report: {report['batch']}",
        "",
        f"- timestamp: `{report['timestamp']}`",
        f"- smoke_json: `{report['source_reports']['smoke_json']}`",
        f"- parity_json: `{report['source_reports']['parity_json']}`",
        f"- smoke_status: `{report['source_status']['smoke']}`",
        f"- parity_status: `{report['source_status']['parity']}`",
        f"- recommendation: `{report['go_no_go_recommendation']}`",
        "",
        "## Blockers",
    ]
    if report["blockers"]:
        lines.extend(f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if report["warnings"]:
        lines.extend(f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["warnings"])
    else:
        lines.append("- none")
    lines.extend(["", "## Skipped"])
    if report["skipped"]:
        lines.extend(f"- `{json.dumps(item, ensure_ascii=False)}`" for item in report["skipped"])
    else:
        lines.append("- none")
    lines.extend(["", "## Side Effect Safety"])
    if report["side_effect_safety"]:
        for key, value in sorted(report["side_effect_safety"].items()):
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- no side-effect safety object found in source reports")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate gray release smoke/parity JSON into a release report.")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--input-json", required=True, help="Selected gray smoke JSON report.")
    parser.add_argument("--parity-json", required=True, help="Selected parity JSON report.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.batch, args.input_json, args.parity_json)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_markdown_report(report, args.output_md)
    write_json_report(report, args.output_json)
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print(f"recommendation: {report['go_no_go_recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
