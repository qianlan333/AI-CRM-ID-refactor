#!/usr/bin/env python3
from __future__ import annotations

import re
import sys


ATTESTATION_PREFIX = "AICRM_ATTESTED_RELEASE_SHA="
ATTESTATION_PATTERN = re.compile(r"AICRM_ATTESTED_RELEASE_SHA=([0-9a-f]{40})")


def extract_release_sha(captured_stdout: str) -> str:
    attestation_lines = [
        line.removesuffix("\r")
        for line in captured_stdout.split("\n")
        if line.startswith(ATTESTATION_PREFIX)
    ]
    if len(attestation_lines) != 1:
        raise ValueError("guarded checkout output must contain exactly one attestation line")
    match = ATTESTATION_PATTERN.fullmatch(attestation_lines[0])
    if match is None:
        raise ValueError("guarded checkout attestation line is malformed")
    return match.group(1)


def main() -> int:
    try:
        release_sha = extract_release_sha(sys.stdin.read())
    except ValueError:
        print("guarded checkout attestation output is invalid", file=sys.stderr)
        return 1
    print(release_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
