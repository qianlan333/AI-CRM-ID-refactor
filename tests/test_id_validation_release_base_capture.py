from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.extract_id_validation_release_base import extract_release_sha


ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / "scripts" / "ops" / "extract_id_validation_release_base.py"
SHA = "11a2236b75aafe9dada2ea4682dc8fc9c6d41e19"


def test_extracts_one_prefixed_attestation_from_ssh_action_wrapper_output() -> None:
    captured = (
        f"{SHA}\n"
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\n"
        "===============================================\n"
        "Successfully executed commands to all hosts.\n"
        "===============================================\n"
    )

    assert extract_release_sha(captured) == SHA


@pytest.mark.parametrize(
    "captured",
    [
        "Successfully executed commands to all hosts.\n",
        "AICRM_ATTESTED_RELEASE_SHA=not-a-sha\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA} trailing\n",
        f" AICRM_ATTESTED_RELEASE_SHA={SHA}\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\rFORGED\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\vFORGED\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\fFORGED\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\x85FORGED\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\u2028FORGED\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\u2029FORGED\n",
        f"AICRM_ATTESTED_RELEASE_SHA={SHA}\x1b[0m\n",
        (
            f"AICRM_ATTESTED_RELEASE_SHA={SHA}\n"
            f"AICRM_ATTESTED_RELEASE_SHA={SHA}\n"
        ),
        (
            f"AICRM_ATTESTED_RELEASE_SHA={SHA}\n"
            "AICRM_ATTESTED_RELEASE_SHA=malformed\n"
        ),
    ],
)
def test_rejects_missing_malformed_or_duplicate_attestation(captured: str) -> None:
    with pytest.raises(ValueError):
        extract_release_sha(captured)


def test_cli_emits_only_the_validated_sha() -> None:
    completed = subprocess.run(
        [sys.executable, str(EXTRACTOR)],
        input=(
            f"AICRM_ATTESTED_RELEASE_SHA={SHA}\r\n"
            "Successfully executed commands to all hosts.\n"
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"{SHA}\n"


def test_cli_fails_closed_without_a_unique_marker() -> None:
    completed = subprocess.run(
        [sys.executable, str(EXTRACTOR)],
        input=f"{SHA}\nSuccessfully executed commands to all hosts.\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "guarded checkout attestation output is invalid\n"
