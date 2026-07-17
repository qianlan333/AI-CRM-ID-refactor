from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from scripts.ops import recover_id_validation_provenance as provenance


REPOSITORY = "qianlan333/AI-CRM-ID-refactor"
RELEASE_SHA = "a" * 40
BASE_SHA = "b" * 40
SOURCE_CI_RUN_ID = "29546203547"
PUBLIC_HEALTH_URL = "https://id-dev.youcangogogo.com/health"


def _payload(**overrides: str) -> dict[str, str]:
    payload = {
        "repository": REPOSITORY,
        "deploy_run_id": "29550000001",
        "deploy_run_attempt": "1",
        "source_ci_run_id": SOURCE_CI_RUN_ID,
        "release_sha": RELEASE_SHA,
        "base_sha": BASE_SHA,
        "bundle_sha256": "c" * 64,
        "environment": "id-validation",
        "public_health_url": PUBLIC_HEALTH_URL,
        "deployed_at": "2026-07-17T01:00:00Z",
    }
    payload.update(overrides)
    return payload


def _write(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _recover(canonical: Path, pending: Path, *, prepared: Path | None = None) -> dict[str, object]:
    return provenance.recover_provenance(
        canonical=canonical,
        pending=pending,
        prepared=prepared,
        expected_repository=REPOSITORY,
        expected_release_sha=RELEASE_SHA,
        expected_source_ci_run_id=SOURCE_CI_RUN_ID,
        expected_deploy_run_id="29550000001",
        current_deploy_run_attempt=2,
        expected_public_health_url=PUBLIC_HEALTH_URL,
        promote_pending=True,
        allow_prepared_recovery=True,
        require_canonical_base_chain=True,
    )


def test_valid_canonical_provenance_quarantines_conflicting_orphan(tmp_path: Path) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    _write(canonical, _payload(source_ci_run_id="123"))
    pending.write_text("not-json", encoding="utf-8")

    result = _recover(canonical, pending)

    assert result["result"] == "canonical_valid"
    assert not pending.exists()
    assert len(list(tmp_path.glob("id-validation.pending.json.quarantine-*"))) == 1


def test_same_sha_noop_promotes_valid_pending_provenance_atomically(tmp_path: Path) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(pending, _payload())

    result = _recover(canonical, pending)

    assert result == {
        "result": "pending_promoted",
        "release_sha": RELEASE_SHA,
        "runtime_commit_evidence": True,
    }
    assert json.loads(canonical.read_text(encoding="utf-8")) == _payload()
    assert not pending.exists()
    assert stat.S_IMODE(canonical.stat().st_mode) == 0o640


def test_new_main_deploy_can_recover_current_live_release_by_canonical_chain(tmp_path: Path) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    prepared = tmp_path / "id-validation.prepared.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(pending, _payload())

    result = provenance.recover_provenance(
        canonical=canonical,
        pending=pending,
        prepared=prepared,
        expected_repository=REPOSITORY,
        expected_release_sha=RELEASE_SHA,
        expected_public_health_url=PUBLIC_HEALTH_URL,
        promote_pending=True,
        allow_prepared_recovery=True,
        require_canonical_base_chain=True,
    )

    assert result["result"] == "pending_promoted"
    assert json.loads(canonical.read_text(encoding="utf-8"))["release_sha"] == RELEASE_SHA
    assert not pending.exists()


def test_prepared_record_requires_explicit_full_readiness_recovery(tmp_path: Path) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    prepared = tmp_path / "id-validation.prepared.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(prepared, _payload())
    kwargs = {
        "canonical": canonical,
        "pending": pending,
        "prepared": prepared,
        "expected_repository": REPOSITORY,
        "expected_release_sha": RELEASE_SHA,
        "expected_public_health_url": PUBLIC_HEALTH_URL,
        "promote_pending": True,
        "require_canonical_base_chain": True,
    }

    with pytest.raises(RuntimeError, match="lacks runtime commit evidence"):
        provenance.recover_provenance(**kwargs, allow_prepared_recovery=False)

    result = provenance.recover_provenance(**kwargs, allow_prepared_recovery=True)
    assert result["result"] == "prepared_promoted"
    assert result["runtime_commit_evidence"] is False


def test_symlink_recovery_record_is_never_followed(tmp_path: Path) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    target = tmp_path / "outside.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(target, _payload())
    pending.symlink_to(target)

    with pytest.raises(RuntimeError, match="not a regular file"):
        provenance.recover_provenance(
            canonical=canonical,
            pending=pending,
            prepared=None,
            expected_repository=REPOSITORY,
            expected_release_sha=RELEASE_SHA,
            expected_public_health_url=PUBLIC_HEALTH_URL,
            promote_pending=True,
            require_canonical_base_chain=True,
        )

    assert pending.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8"))["release_sha"] == RELEASE_SHA


@pytest.mark.parametrize(
    "override",
    (
        {"release_sha": "d" * 40},
        {"source_ci_run_id": "999"},
        {"bundle_sha256": "invalid"},
        {"repository": "qianlan333/AI-CRM"},
    ),
)
def test_invalid_pending_provenance_never_replaces_canonical(
    tmp_path: Path, override: dict[str, str]
) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(pending, _payload(**override))

    with pytest.raises(RuntimeError, match="no matching recovery"):
        _recover(canonical, pending)

    assert json.loads(canonical.read_text(encoding="utf-8"))["release_sha"] == BASE_SHA
    assert pending.exists()


def test_failed_atomic_replace_is_recoverable_by_same_sha_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(pending, _payload())
    real_replace = os.replace

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated atomic publish failure")

    monkeypatch.setattr(provenance.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated atomic publish failure"):
        _recover(canonical, pending)
    assert pending.exists()
    assert json.loads(canonical.read_text(encoding="utf-8"))["release_sha"] == BASE_SHA

    monkeypatch.setattr(provenance.os, "replace", real_replace)
    assert _recover(canonical, pending)["result"] == "pending_promoted"
    assert not pending.exists()
    assert json.loads(canonical.read_text(encoding="utf-8"))["release_sha"] == RELEASE_SHA


def test_atomic_publish_fsyncs_file_before_rename_and_directory_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = tmp_path / "id-validation.json"
    pending = tmp_path / "id-validation.pending.json"
    _write(canonical, _payload(release_sha=BASE_SHA, base_sha="d" * 40))
    _write(pending, _payload())
    events: list[str] = []
    real_sync_file = provenance._sync_regular_file
    real_replace = provenance.os.replace
    real_sync_directory = provenance._sync_directory

    def sync_file(record: provenance.ProvenanceFile) -> int:
        events.append("file_fsync")
        return real_sync_file(record)

    def replace(source: Path, target: Path) -> None:
        events.append("replace")
        real_replace(source, target)

    def sync_directory(directory: Path) -> None:
        events.append("directory_fsync")
        real_sync_directory(directory)

    monkeypatch.setattr(provenance, "_sync_regular_file", sync_file)
    monkeypatch.setattr(provenance.os, "replace", replace)
    monkeypatch.setattr(provenance, "_sync_directory", sync_directory)

    _recover(canonical, pending)

    assert events[:3] == ["file_fsync", "replace", "directory_fsync"]
