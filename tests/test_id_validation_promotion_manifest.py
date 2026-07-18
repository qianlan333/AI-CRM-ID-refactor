from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ci.check_id_validation_promotion_manifest import (
    CLASS_ID_ONLY,
    CLASS_MIXED_REVIEW,
    CLASS_NOT_APPLICATION,
    CLASS_PROMOTABLE,
    classify_path,
    load_manifest,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/architecture/id_validation_promotion_manifest.yml"


def test_current_id_validation_promotion_manifest_is_safe() -> None:
    manifest = load_manifest(MANIFEST)

    assert validate_manifest(root=ROOT, manifest=manifest) == []
    assert manifest["authorization"]["command"] == "PROMOTE <validated_ID_SHA> TO AI-CRM"
    assert (
        classify_path(
            "aicrm_next/platform_foundation/execution_runtime/listener.py",
            manifest,
        )
        == CLASS_PROMOTABLE
    )
    assert (
        classify_path(".github/workflows/id-validation-queue-operations.yml", manifest)
        == CLASS_ID_ONLY
    )
    assert (
        classify_path(
            "aicrm_next/platform_foundation/external_effects/adapters.py",
            manifest,
        )
        == CLASS_MIXED_REVIEW
    )
    assert classify_path("README.md", manifest) == CLASS_NOT_APPLICATION


def test_manifest_rejects_missing_fail_closed_id_overlay_classification(tmp_path: Path) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    manifest["id_only_overlay"]["paths"].remove(".github/workflows/deploy.yml")

    errors = validate_manifest(root=ROOT, manifest=manifest)

    assert any(
        ".github/workflows/deploy.yml must be id_only" in error
        for error in errors
    )


def test_manifest_rejects_ambiguous_guarded_path() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    manifest["mixed_review_required"]["paths"].append(
        "aicrm_next/platform_foundation/external_effects/wecom_canary_policy.py"
    )

    errors = validate_manifest(root=ROOT, manifest=manifest)

    assert any("matches both id_only and mixed_review_required" in error for error in errors)
