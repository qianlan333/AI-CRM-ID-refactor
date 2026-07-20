from __future__ import annotations

from scripts.ci.classify_id_validation_runtime_impact import (
    TreeEntry,
    classify_runtime_impact,
    is_runtime_path,
)


def _entry(path: str, oid: str, *, mode: str = "100644") -> TreeEntry:
    return TreeEntry(mode=mode, object_type="blob", oid=oid, path=path)


def test_runtime_impact_ignores_only_explicit_source_only_paths() -> None:
    assert not is_runtime_path("docs/ci/pytest_duration_baseline.json")
    assert not is_runtime_path("tests/test_queue_runtime_validation.py")
    assert not is_runtime_path(".github/workflows/ci-fast.yml")
    assert not is_runtime_path("scripts/ci/select_test_scope.py")
    assert not is_runtime_path("AGENTS.md")
    assert not is_runtime_path("README.md")

    assert is_runtime_path("aicrm_next/main.py")
    assert is_runtime_path("scripts/ops/manage_queue_runtime_soak.py")
    assert is_runtime_path("deploy/production_runtime_units.json")
    assert is_runtime_path("pyproject.toml")
    assert is_runtime_path("unknown-root-file.txt")


def test_source_only_changes_keep_runtime_digest_and_change_validation_digest() -> None:
    base = {
        "aicrm_next/main.py": _entry("aicrm_next/main.py", "a" * 40),
        "docs/guide.md": _entry("docs/guide.md", "b" * 40),
        "tests/test_main.py": _entry("tests/test_main.py", "c" * 40),
    }
    target = {
        **base,
        "docs/guide.md": _entry("docs/guide.md", "d" * 40),
        "tests/test_main.py": _entry("tests/test_main.py", "e" * 40),
        ".github/workflows/ci-fast.yml": _entry(
            ".github/workflows/ci-fast.yml", "f" * 40
        ),
    }

    result = classify_runtime_impact(base, target)

    assert result["runtime_required"] is False
    assert result["runtime_base_digest"] == result["runtime_target_digest"]
    assert result["validation_base_digest"] != result["validation_target_digest"]
    assert result["changed_paths"] == [
        ".github/workflows/ci-fast.yml",
        "docs/guide.md",
        "tests/test_main.py",
    ]
    assert result["runtime_changed_paths"] == []


def test_runtime_or_unknown_path_change_fails_closed() -> None:
    base = {
        "aicrm_next/main.py": _entry("aicrm_next/main.py", "a" * 40),
        "pyproject.toml": _entry("pyproject.toml", "b" * 40),
    }
    target = {
        "aicrm_next/main.py": _entry("aicrm_next/main.py", "c" * 40),
        "pyproject.toml": _entry("pyproject.toml", "b" * 40),
        "new-root-file.txt": _entry("new-root-file.txt", "d" * 40),
    }

    result = classify_runtime_impact(base, target)

    assert result["runtime_required"] is True
    assert result["runtime_changed_paths"] == [
        "aicrm_next/main.py",
        "new-root-file.txt",
    ]
    assert result["runtime_base_digest"] != result["runtime_target_digest"]


def test_runtime_digest_includes_mode_changes() -> None:
    base = {"scripts/ops/example.py": _entry("scripts/ops/example.py", "a" * 40)}
    target = {
        "scripts/ops/example.py": _entry(
            "scripts/ops/example.py", "a" * 40, mode="100755"
        )
    }

    result = classify_runtime_impact(base, target)

    assert result["runtime_required"] is True
    assert result["runtime_changed_paths"] == ["scripts/ops/example.py"]
