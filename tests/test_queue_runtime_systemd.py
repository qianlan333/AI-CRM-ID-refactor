from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNITS = {
    "aicrm-internal-queue-runtime.service": "internal",
    "aicrm-inbox-queue-runtime.service": "webhook",
    "aicrm-external-queue-runtime.service": "external",
}


def test_queue_runtime_units_are_registered_as_claimless_persistent_services() -> None:
    manifest = json.loads((ROOT / "deploy" / "production_runtime_units.json").read_text(encoding="utf-8"))
    active = {str(item.get("service")): item for item in manifest.get("active_services") or []}

    for unit, queue_kind in UNITS.items():
        item = active[unit]
        assert item["stop_for_migration"] is True
        body = (ROOT / "deploy" / unit).read_text(encoding="utf-8")
        assert "Restart=always" in body
        assert "AICRM_QUEUE_WORKER_GENERATION=0" in body
        assert "AICRM_LISTENER_DATABASE_URL" in body
        assert f"run_execution_runtime.py --queue-kind {queue_kind} --generation 0" in body
        assert " --execute" not in body


def test_queue_runtime_execute_mode_requires_positive_generation() -> None:
    script = (ROOT / "scripts" / "run_execution_runtime.py").read_text(encoding="utf-8")
    assert 'if args.execute and args.generation <= 0:' in script
    assert 'parser.error("--execute requires --generation > 0")' in script
