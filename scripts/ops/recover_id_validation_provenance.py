from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
BUNDLE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProvenanceFile:
    path: Path
    payload: dict[str, Any] | None
    raw: bytes
    device: int
    inode: int


def _read_regular_file(path: Path) -> ProvenanceFile | None:
    try:
        path_info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(path_info.st_mode):
        raise RuntimeError(f"provenance path is not a regular file: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        file_info = os.fstat(descriptor)
        if not stat.S_ISREG(file_info.st_mode):
            raise RuntimeError(f"provenance descriptor is not a regular file: {path.name}")
        if (int(file_info.st_dev), int(file_info.st_ino)) != (
            int(path_info.st_dev),
            int(path_info.st_ino),
        ):
            raise RuntimeError(f"provenance path changed while opening: {path.name}")
        if file_info.st_uid != os.geteuid():
            raise RuntimeError(f"provenance file owner mismatch: {path.name}")
        if stat.S_IMODE(file_info.st_mode) & 0o022:
            raise RuntimeError(f"provenance file is group/world writable: {path.name}")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            raw = stream.read()
    finally:
        os.close(descriptor)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded = None
    payload = decoded if isinstance(decoded, dict) else None
    return ProvenanceFile(
        path=path,
        payload=payload,
        raw=raw,
        device=int(file_info.st_dev),
        inode=int(file_info.st_ino),
    )


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_regular_file(record: ProvenanceFile) -> int:
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(record.path, flags)
    current = os.fstat(descriptor)
    if (int(current.st_dev), int(current.st_ino)) != (record.device, record.inode):
        os.close(descriptor)
        raise RuntimeError("provenance source changed during validation")
    os.fchmod(descriptor, 0o640)
    os.fsync(descriptor)
    return descriptor


def _atomic_publish(record: ProvenanceFile, target: Path) -> None:
    # The workflow holds the target-specific deploy lock and the release directory
    # is not group/world writable. Keep the validated inode open across rename as
    # an additional fail-closed check within that single release-owner boundary.
    descriptor = _sync_regular_file(record)
    try:
        current = os.lstat(record.path)
        if (int(current.st_dev), int(current.st_ino)) != (record.device, record.inode):
            raise RuntimeError("provenance source path changed before atomic publish")
        os.replace(record.path, target)
        published = os.lstat(target)
        if (int(published.st_dev), int(published.st_ino)) != (record.device, record.inode):
            raise RuntimeError("published provenance inode does not match the validated source")
        _sync_directory(target.parent)
    finally:
        os.close(descriptor)


def _durable_unlink(record: ProvenanceFile) -> None:
    current = os.lstat(record.path)
    if (int(current.st_dev), int(current.st_ino)) != (record.device, record.inode):
        raise RuntimeError("provenance orphan changed before cleanup")
    record.path.unlink()
    _sync_directory(record.path.parent)


def _quarantine(path: Path, *, expected: ProvenanceFile | None = None) -> Path:
    initial = os.lstat(path)
    if expected is not None and (int(initial.st_dev), int(initial.st_ino)) != (
        expected.device,
        expected.inode,
    ):
        raise RuntimeError("provenance orphan changed before quarantine")
    raw = expected.raw if expected is not None else path.name.encode()
    digest = hashlib.sha256(raw).hexdigest()[:12]
    target = path.with_name(f"{path.name}.quarantine-{time.time_ns()}-{digest}")
    current = os.lstat(path)
    if (int(current.st_dev), int(current.st_ino)) != (int(initial.st_dev), int(initial.st_ino)):
        raise RuntimeError("provenance orphan changed during quarantine")
    os.replace(path, target)
    _sync_directory(path.parent)
    return target


def _numeric_string(value: Any) -> bool:
    return isinstance(value, str) and value.isdigit() and int(value) > 0


def _valid_payload(
    payload: dict[str, Any] | None,
    *,
    expected_repository: str,
    expected_public_health_url: str,
    expected_release_sha: str | None = None,
    expected_source_ci_run_id: str | None = None,
    expected_deploy_run_id: str | None = None,
    expected_base_sha: str | None = None,
    expected_bundle_sha256: str | None = None,
    current_deploy_run_attempt: int | None = None,
) -> bool:
    if payload is None:
        return False
    valid = (
        payload.get("repository") == expected_repository
        and payload.get("environment") == "id-validation"
        and FULL_SHA.fullmatch(str(payload.get("release_sha") or "")) is not None
        and payload.get("public_health_url") == expected_public_health_url
        and FULL_SHA.fullmatch(str(payload.get("base_sha") or "")) is not None
        and BUNDLE_SHA256.fullmatch(str(payload.get("bundle_sha256") or "")) is not None
        and _numeric_string(payload.get("source_ci_run_id"))
        and _numeric_string(payload.get("deploy_run_id"))
        and _numeric_string(payload.get("deploy_run_attempt"))
        and isinstance(payload.get("deployed_at"), str)
        and bool(payload.get("deployed_at"))
    )
    exact_pairs = (
        ("release_sha", expected_release_sha),
        ("source_ci_run_id", expected_source_ci_run_id),
        ("deploy_run_id", expected_deploy_run_id),
        ("base_sha", expected_base_sha),
        ("bundle_sha256", expected_bundle_sha256),
    )
    valid = valid and all(expected is None or payload.get(key) == expected for key, expected in exact_pairs)
    if current_deploy_run_attempt is not None and expected_deploy_run_id is not None:
        valid = valid and int(payload.get("deploy_run_attempt") or 0) < int(current_deploy_run_attempt)
    return valid


def _clean_orphan(candidate: Path, canonical_payload: dict[str, Any]) -> str:
    try:
        candidate_file = _read_regular_file(candidate)
    except RuntimeError:
        return f"quarantined:{_quarantine(candidate).name}"
    if candidate_file is None:
        return "absent"
    if candidate_file.payload == canonical_payload:
        _durable_unlink(candidate_file)
        return "removed_duplicate"
    return f"quarantined:{_quarantine(candidate, expected=candidate_file).name}"


def _is_git_ancestor(repository: Path, base_sha: str, release_sha: str) -> bool:
    completed = subprocess.run(  # noqa: S603 - fixed git argv, no shell
        ["git", "-C", str(repository), "merge-base", "--is-ancestor", base_sha, release_sha],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def recover_provenance(
    *,
    canonical: Path,
    pending: Path,
    prepared: Path | None,
    expected_repository: str,
    expected_release_sha: str,
    expected_public_health_url: str,
    expected_source_ci_run_id: str | None = None,
    expected_deploy_run_id: str | None = None,
    expected_base_sha: str | None = None,
    expected_bundle_sha256: str | None = None,
    current_deploy_run_attempt: int | None = None,
    repository_path: Path | None = None,
    promote_pending: bool = False,
    allow_prepared_recovery: bool = False,
    require_canonical_base_chain: bool = False,
) -> dict[str, Any]:
    candidates = [path for path in (pending, prepared) if path is not None]
    if any(path.parent.resolve() != canonical.parent.resolve() for path in candidates):
        raise ValueError("canonical and recovery provenance must share one directory")
    if FULL_SHA.fullmatch(expected_release_sha) is None:
        raise ValueError("expected release SHA must be a full lowercase SHA")
    canonical_file = _read_regular_file(canonical)
    canonical_payload = canonical_file.payload if canonical_file else None
    canonical_valid = _valid_payload(
        canonical_payload,
        expected_repository=expected_repository,
        expected_release_sha=expected_release_sha,
        expected_public_health_url=expected_public_health_url,
    )
    existing_candidates = [path for path in candidates if os.path.lexists(path)]
    if canonical_valid:
        orphan_results = {
            path.name: _clean_orphan(path, canonical_payload or {}) for path in existing_candidates
        }
        return {
            "result": "canonical_valid",
            "release_sha": expected_release_sha,
            "orphan_recovery": orphan_results,
        }
    if not promote_pending:
        raise RuntimeError("canonical ID validation provenance mismatch")
    if len(existing_candidates) != 1:
        raise RuntimeError("exactly one pending or prepared provenance record is required")
    source_path = existing_candidates[0]
    if prepared is not None and source_path == prepared and not allow_prepared_recovery:
        raise RuntimeError("prepared provenance lacks runtime commit evidence")
    source = _read_regular_file(source_path)
    if source is None or not _valid_payload(
        source.payload,
        expected_repository=expected_repository,
        expected_release_sha=expected_release_sha,
        expected_public_health_url=expected_public_health_url,
        expected_source_ci_run_id=expected_source_ci_run_id,
        expected_deploy_run_id=expected_deploy_run_id,
        expected_base_sha=expected_base_sha,
        expected_bundle_sha256=expected_bundle_sha256,
        current_deploy_run_attempt=current_deploy_run_attempt,
    ):
        raise RuntimeError("canonical provenance is invalid and no matching recovery record is available")
    if require_canonical_base_chain:
        canonical_release_sha = str((canonical_payload or {}).get("release_sha") or "")
        if not _valid_payload(
            canonical_payload,
            expected_repository=expected_repository,
            expected_public_health_url=expected_public_health_url,
        ) or str((source.payload or {}).get("base_sha") or "") != canonical_release_sha:
            raise RuntimeError("recovery provenance does not extend the canonical release chain")
        if repository_path is not None and not _is_git_ancestor(
            repository_path, canonical_release_sha, expected_release_sha
        ):
            raise RuntimeError("recovery provenance base is not an ancestor of the live release")
    _atomic_publish(source, canonical)
    promoted = _read_regular_file(canonical)
    if promoted is None or not _valid_payload(
        promoted.payload,
        expected_repository=expected_repository,
        expected_release_sha=expected_release_sha,
        expected_public_health_url=expected_public_health_url,
        expected_source_ci_run_id=expected_source_ci_run_id,
        expected_deploy_run_id=expected_deploy_run_id,
        expected_base_sha=expected_base_sha,
        expected_bundle_sha256=expected_bundle_sha256,
    ):
        raise RuntimeError("promoted provenance failed post-commit validation")
    return {
        "result": "prepared_promoted" if prepared is not None and source_path == prepared else "pending_promoted",
        "release_sha": expected_release_sha,
        "runtime_commit_evidence": source_path == pending,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or recover ID validation release provenance.")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--expected-public-health-url", required=True)
    parser.add_argument("--expected-source-ci-run-id")
    parser.add_argument("--expected-deploy-run-id")
    parser.add_argument("--expected-base-sha")
    parser.add_argument("--expected-bundle-sha256")
    parser.add_argument("--current-deploy-run-attempt", type=int)
    parser.add_argument("--repository-path", type=Path)
    parser.add_argument("--promote-pending", action="store_true")
    parser.add_argument("--allow-prepared-recovery", action="store_true")
    parser.add_argument("--require-canonical-base-chain", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = recover_provenance(
            canonical=args.canonical,
            pending=args.pending,
            prepared=args.prepared,
            expected_repository=args.expected_repository,
            expected_release_sha=args.expected_release_sha,
            expected_source_ci_run_id=args.expected_source_ci_run_id,
            expected_deploy_run_id=args.expected_deploy_run_id,
            expected_base_sha=args.expected_base_sha,
            expected_bundle_sha256=args.expected_bundle_sha256,
            current_deploy_run_attempt=args.current_deploy_run_attempt,
            repository_path=args.repository_path,
            expected_public_health_url=args.expected_public_health_url,
            promote_pending=args.promote_pending,
            allow_prepared_recovery=args.allow_prepared_recovery,
            require_canonical_base_chain=args.require_canonical_base_chain,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
