#!/usr/bin/env python3
"""Select one deterministic, file-preserving pytest shard for CI."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ShardSelection:
    index: int
    files: tuple[str, ...]
    item_count: int


def parse_collected_nodeids(output: str) -> list[str]:
    """Return pytest node IDs from quiet collection output."""

    nodeids: list[str] = []
    for raw_line in output.splitlines():
        nodeid = raw_line.strip()
        if not nodeid.startswith("tests/") or "::" not in nodeid:
            continue
        file_path = nodeid.split("::", 1)[0]
        if not file_path.endswith(".py"):
            continue
        nodeids.append(nodeid)
    return nodeids


def _validated_nodeids(nodeids: Iterable[str]) -> list[str]:
    normalized = sorted(str(nodeid).strip() for nodeid in nodeids if str(nodeid).strip())
    if not normalized:
        raise ValueError("no pytest node IDs were collected")
    duplicates = [nodeid for nodeid, count in Counter(normalized).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate pytest node ID: {duplicates[0]}")
    for nodeid in normalized:
        file_path, separator, _ = nodeid.partition("::")
        if not separator or not file_path.startswith("tests/") or not file_path.endswith(".py"):
            raise ValueError(f"invalid pytest node ID: {nodeid}")
    return normalized


def partition_nodeids_by_file(nodeids: Iterable[str], *, shard_total: int) -> tuple[ShardSelection, ...]:
    """Greedily balance collected item counts without splitting test files."""

    if shard_total <= 0:
        raise ValueError("shard_total must be positive")
    normalized = _validated_nodeids(nodeids)
    file_counts = Counter(nodeid.split("::", 1)[0] for nodeid in normalized)
    if len(file_counts) < shard_total:
        raise ValueError("shard_total exceeds the number of collected test files")

    shard_files: list[list[str]] = [[] for _ in range(shard_total)]
    shard_item_counts = [0 for _ in range(shard_total)]
    for file_path, item_count in sorted(file_counts.items(), key=lambda item: (-item[1], item[0])):
        shard_index = min(
            range(shard_total),
            key=lambda index: (shard_item_counts[index], len(shard_files[index]), index),
        )
        shard_files[shard_index].append(file_path)
        shard_item_counts[shard_index] += item_count

    return tuple(
        ShardSelection(
            index=index,
            files=tuple(sorted(shard_files[index])),
            item_count=shard_item_counts[index],
        )
        for index in range(shard_total)
    )


def select_shard(nodeids: Iterable[str], *, shard_index: int, shard_total: int) -> tuple[ShardSelection, ...]:
    if shard_total <= 0:
        raise ValueError("shard_total must be positive")
    if shard_index < 0 or shard_index >= shard_total:
        raise ValueError("shard_index must be within [0, shard_total)")
    shards = partition_nodeids_by_file(nodeids, shard_total=shard_total)
    if not shards[shard_index].files:
        raise ValueError(f"pytest shard {shard_index} is empty")
    return shards


def collect_pytest_nodeids() -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--collect-only",
        "-q",
        "--disable-warnings",
        "--color=no",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        diagnostic = "\n".join((completed.stdout + "\n" + completed.stderr).splitlines()[-40:])
        raise RuntimeError(f"pytest collection failed with exit code {completed.returncode}:\n{diagnostic}")
    nodeids = parse_collected_nodeids(completed.stdout)
    if not nodeids:
        raise RuntimeError("pytest collection succeeded but returned no test node IDs")
    return nodeids


def _write_selected_files(path: Path, files: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        handle.write("\n".join(files))
        handle.write("\n")
    os.replace(temporary_path, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-total", type=int, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        nodeids = collect_pytest_nodeids()
        shards = select_shard(
            nodeids,
            shard_index=args.shard_index,
            shard_total=args.shard_total,
        )
        selected = shards[args.shard_index]
        _write_selected_files(args.output_file, selected.files)
    except (OSError, RuntimeError, ValueError):
        print(json.dumps({"error": "pytest shard selection failed", "ok": False}, sort_keys=True), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "selected_files": len(selected.files),
                "selected_items": selected.item_count,
                "shard_index": selected.index,
                "shard_item_counts": [shard.item_count for shard in shards],
                "shard_total": len(shards),
                "total_files": sum(len(shard.files) for shard in shards),
                "total_items": len(nodeids),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
