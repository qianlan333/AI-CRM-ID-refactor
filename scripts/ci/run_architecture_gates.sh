#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python"
fi

"$PYTHON" tools/check_route_ownership_manifest.py
"$PYTHON" tools/check_architecture_boundaries.py
"$PYTHON" tools/check_external_effects_boundary.py
"$PYTHON" tools/check_db_access_boundary.py
"$PYTHON" tools/check_background_job_contract.py
"$PYTHON" tools/check_data_table_lifecycle.py
