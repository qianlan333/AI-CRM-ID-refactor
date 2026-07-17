from __future__ import annotations

import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "scripts" / "ops" / "resolve_id_validation_release_base.sh"
EXPECTED_REPOSITORY = "qianlan333/AI-CRM-ID-refactor"
EXPECTED_HEALTH_URL = "https://id-dev.youcangogogo.com/health"


@dataclass(frozen=True)
class ResolverFixture:
    root: Path
    repository: Path
    provenance_directory: Path
    canonical_path: Path
    canonical_sha: str
    current_sha: str
    environment: dict[str, str]


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _provenance_payload(fixture: ResolverFixture, **overrides: str) -> dict[str, str]:
    payload = {
        "repository": EXPECTED_REPOSITORY,
        "environment": "id-validation",
        "public_health_url": EXPECTED_HEALTH_URL,
        "release_sha": fixture.canonical_sha,
        "base_sha": fixture.canonical_sha,
        "bundle_sha256": "a" * 64,
        "source_ci_run_id": "101",
        "deploy_run_id": "202",
        "deploy_run_attempt": "1",
    }
    payload.update(overrides)
    return payload


def _write_provenance(fixture: ResolverFixture, **overrides: str) -> None:
    fixture.canonical_path.write_text(
        json.dumps(_provenance_payload(fixture, **overrides), sort_keys=True),
        encoding="utf-8",
    )
    fixture.canonical_path.chmod(0o640)


@pytest.fixture()
def resolver_fixture(tmp_path: Path) -> ResolverFixture:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "AI CRM CI")
    _git(repository, "config", "user.email", "ci@example.invalid")
    _git(repository, "remote", "add", "origin", f"https://github.com/{EXPECTED_REPOSITORY}.git")

    (repository / ".gitignore").write_text(".release-sha\n", encoding="utf-8")
    (repository / "root.txt").write_text("canonical\n", encoding="utf-8")
    _git(repository, "add", ".gitignore", "root.txt")
    _git(repository, "commit", "-m", "canonical release")
    canonical_sha = _git(repository, "rev-parse", "HEAD")

    (repository / "current.txt").write_text("guarded checkout\n", encoding="utf-8")
    _git(repository, "add", "current.txt")
    _git(repository, "commit", "-m", "guarded checkout")
    current_sha = _git(repository, "rev-parse", "HEAD")
    (repository / ".release-sha").write_text(f"{current_sha}\n", encoding="utf-8")

    provenance_directory = tmp_path / "releases"
    provenance_directory.mkdir()
    provenance_directory.chmod(0o750)
    canonical_path = provenance_directory / "id-validation.json"

    shim_directory = tmp_path / "bin"
    shim_directory.mkdir()
    flock = shim_directory / "flock"
    flock.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    flock.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "EXPECTED_REPOSITORY": EXPECTED_REPOSITORY,
            "DEPLOY_TARGET": "id-validation",
            "PUBLIC_HEALTH_URL": EXPECTED_HEALTH_URL,
            "PATH": f"{shim_directory}{os.pathsep}{environment['PATH']}",
        }
    )
    fixture = ResolverFixture(
        root=tmp_path,
        repository=repository,
        provenance_directory=provenance_directory,
        canonical_path=canonical_path,
        canonical_sha=canonical_sha,
        current_sha=current_sha,
        environment=environment,
    )
    _write_provenance(fixture)
    return fixture


def _run_resolver(fixture: ResolverFixture) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RESOLVER), str(fixture.canonical_path), str(fixture.repository)],
        cwd=fixture.root,
        env=fixture.environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_failed(fixture: ResolverFixture, message: str) -> None:
    completed = _run_resolver(fixture)

    assert completed.returncode != 0
    assert message in f"{completed.stdout}\n{completed.stderr}"


def test_guarded_resolver_outputs_current_checkout_head_not_stale_canonical_release(
    resolver_fixture: ResolverFixture,
) -> None:
    assert RESOLVER.stat().st_mode & stat.S_IXUSR

    completed = _run_resolver(resolver_fixture)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"{resolver_fixture.current_sha}\n"
    assert completed.stdout.strip() != resolver_fixture.canonical_sha


def test_guarded_resolver_rejects_dirty_checkout(resolver_fixture: ResolverFixture) -> None:
    (resolver_fixture.repository / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    _assert_failed(resolver_fixture, "refuses a dirty server checkout")


def test_guarded_resolver_rejects_release_marker_mismatch(
    resolver_fixture: ResolverFixture,
) -> None:
    (resolver_fixture.repository / ".release-sha").write_text(
        f"{resolver_fixture.canonical_sha}\n",
        encoding="utf-8",
    )

    _assert_failed(resolver_fixture, "release marker does not match")


def test_guarded_resolver_rejects_split_lines_that_concatenate_to_a_sha(
    resolver_fixture: ResolverFixture,
) -> None:
    current_sha = resolver_fixture.current_sha
    (resolver_fixture.repository / ".release-sha").write_text(
        f"{current_sha[:20]}\n{current_sha[20:]}",
        encoding="utf-8",
    )

    _assert_failed(resolver_fixture, "release marker is not exactly one SHA")


def test_guarded_resolver_rejects_canonical_release_outside_current_ancestry(
    resolver_fixture: ResolverFixture,
) -> None:
    tree_sha = _git(resolver_fixture.repository, "rev-parse", "HEAD^{tree}")
    divergent_sha = _git(
        resolver_fixture.repository,
        "commit-tree",
        tree_sha,
        "-p",
        resolver_fixture.canonical_sha,
        "-m",
        "divergent canonical provenance",
    )
    _write_provenance(resolver_fixture, release_sha=divergent_sha)

    _assert_failed(resolver_fixture, "not descended from canonical provenance")


def test_guarded_resolver_rejects_canonical_base_outside_release_ancestry(
    resolver_fixture: ResolverFixture,
) -> None:
    tree_sha = _git(resolver_fixture.repository, "rev-parse", "HEAD^{tree}")
    divergent_sha = _git(
        resolver_fixture.repository,
        "commit-tree",
        tree_sha,
        "-m",
        "divergent canonical base",
    )
    _write_provenance(resolver_fixture, base_sha=divergent_sha)

    _assert_failed(
        resolver_fixture,
        "canonical base is not an ancestor of the canonical release",
    )


@pytest.mark.parametrize("state", ["pending", "prepared"])
def test_guarded_resolver_rejects_ambiguous_provenance_state(
    resolver_fixture: ResolverFixture,
    state: str,
) -> None:
    (resolver_fixture.provenance_directory / f"id-validation.{state}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    _assert_failed(resolver_fixture, "ambiguous pending or prepared provenance")


def test_guarded_resolver_rejects_non_id_repository_origin(
    resolver_fixture: ResolverFixture,
) -> None:
    _git(
        resolver_fixture.repository,
        "remote",
        "set-url",
        "origin",
        "https://github.com/qianlan333/AI-CRM.git",
    )

    _assert_failed(resolver_fixture, "refuses a non-ID repository checkout")


@pytest.mark.parametrize(
    ("path_kind", "mode", "message"),
    [
        ("directory", 0o700, "directory mode must be 0750"),
        ("file", 0o600, "file mode must be 0640"),
    ],
)
def test_guarded_resolver_rejects_insecure_or_unexpected_provenance_modes(
    resolver_fixture: ResolverFixture,
    path_kind: str,
    mode: int,
    message: str,
) -> None:
    target = (
        resolver_fixture.provenance_directory
        if path_kind == "directory"
        else resolver_fixture.canonical_path
    )
    target.chmod(mode)

    _assert_failed(resolver_fixture, message)


def test_guarded_resolver_rejects_malformed_canonical_json(
    resolver_fixture: ResolverFixture,
) -> None:
    resolver_fixture.canonical_path.write_text("{\n", encoding="utf-8")
    resolver_fixture.canonical_path.chmod(0o640)

    _assert_failed(resolver_fixture, "JSONDecodeError")


def test_guarded_resolver_rejects_symlinked_canonical_provenance(
    resolver_fixture: ResolverFixture,
) -> None:
    symlink_target = resolver_fixture.root / "untrusted-provenance.json"
    symlink_target.write_text(
        json.dumps(_provenance_payload(resolver_fixture)),
        encoding="utf-8",
    )
    symlink_target.chmod(0o640)
    resolver_fixture.canonical_path.unlink()
    resolver_fixture.canonical_path.symlink_to(symlink_target)

    _assert_failed(resolver_fixture, "missing or is a symlink")
