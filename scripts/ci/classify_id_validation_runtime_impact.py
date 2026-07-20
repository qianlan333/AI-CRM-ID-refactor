#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.shared.sensitive_data import redact_sensitive_text  # noqa: E402


SOURCE_ONLY_PREFIXES = (
    ".github/",
    "docs/",
    "scripts/ci/",
    "tests/",
)
SOURCE_ONLY_ROOT_FILES = frozenset(
    {
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
    }
)


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    object_type: str
    oid: str
    path: str


def is_runtime_path(path: str) -> bool:
    normalized = str(path or "").strip("/")
    if not normalized:
        return True
    if normalized in SOURCE_ONLY_ROOT_FILES:
        return False
    return not any(normalized.startswith(prefix) for prefix in SOURCE_ONLY_PREFIXES)


def _tree_digest(entries: Iterable[TreeEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item.path):
        digest.update(
            (
                f"{entry.mode} {entry.object_type} {entry.oid}\t{entry.path}\0"
            ).encode("utf-8", errors="surrogateescape")
        )
    return digest.hexdigest()


def classify_runtime_impact(
    base_entries: Mapping[str, TreeEntry],
    target_entries: Mapping[str, TreeEntry],
) -> dict[str, object]:
    changed_paths = sorted(
        path
        for path in set(base_entries) | set(target_entries)
        if base_entries.get(path) != target_entries.get(path)
    )
    runtime_changed_paths = [path for path in changed_paths if is_runtime_path(path)]
    base_runtime = [entry for path, entry in base_entries.items() if is_runtime_path(path)]
    target_runtime = [
        entry for path, entry in target_entries.items() if is_runtime_path(path)
    ]
    base_validation = [
        entry for path, entry in base_entries.items() if not is_runtime_path(path)
    ]
    target_validation = [
        entry for path, entry in target_entries.items() if not is_runtime_path(path)
    ]
    runtime_base_digest = _tree_digest(base_runtime)
    runtime_target_digest = _tree_digest(target_runtime)
    result: dict[str, object] = {
        "runtime_required": runtime_base_digest != runtime_target_digest,
        "runtime_base_digest": runtime_base_digest,
        "runtime_target_digest": runtime_target_digest,
        "validation_base_digest": _tree_digest(base_validation),
        "validation_target_digest": _tree_digest(target_validation),
        "changed_path_count": len(changed_paths),
        "runtime_changed_path_count": len(runtime_changed_paths),
        "changed_paths": changed_paths,
        "runtime_changed_paths": runtime_changed_paths,
    }
    classification_payload = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    result["classification_digest"] = hashlib.sha256(classification_payload).hexdigest()
    return result


def _git_tree_entries(repository: Path, ref: str) -> dict[str, TreeEntry]:
    completed = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", ref],
        cwd=repository,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot inspect git tree {ref}: {message}")
    entries: dict[str, TreeEntry] = {}
    for raw_entry in completed.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, separator, raw_path = raw_entry.partition(b"\t")
        if not separator:
            raise RuntimeError(f"invalid git tree entry for {ref}")
        parts = metadata.decode("ascii").split(" ")
        if len(parts) != 3:
            raise RuntimeError(f"invalid git tree metadata for {ref}")
        mode, object_type, oid = parts
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if not path or path in entries:
            raise RuntimeError(f"invalid or duplicate git tree path for {ref}")
        entries[path] = TreeEntry(
            mode=mode,
            object_type=object_type,
            oid=oid,
            path=path,
        )
    return entries


def classify_refs(repository: Path, base_ref: str, target_ref: str) -> dict[str, object]:
    result = classify_runtime_impact(
        _git_tree_entries(repository, base_ref),
        _git_tree_entries(repository, target_ref),
    )
    return {
        "base_ref": base_ref,
        "target_ref": target_ref,
        **result,
        "source_only_policy": {
            "prefixes": list(SOURCE_ONLY_PREFIXES),
            "root_files": sorted(SOURCE_ONLY_ROOT_FILES),
            "unknown_paths_fail_closed": True,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify whether an ID-validation source change alters runtime bytes.",
    )
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def _write_github_output(path: Path, result: Mapping[str, object]) -> None:
    keys = (
        "runtime_required",
        "runtime_base_digest",
        "runtime_target_digest",
        "validation_base_digest",
        "validation_target_digest",
        "classification_digest",
        "changed_path_count",
        "runtime_changed_path_count",
    )
    with path.open("a", encoding="utf-8") as handle:
        for key in keys:
            value = result[key]
            if isinstance(value, bool):
                value = str(value).lower()
            handle.write(f"{key}={value}\n")


def main() -> int:
    args = _parse_args()
    result = classify_refs(
        args.repository.resolve(),
        str(args.base_ref).strip(),
        str(args.target_ref).strip(),
    )
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    if args.github_output:
        _write_github_output(args.github_output, result)
    print(redact_sensitive_text(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
