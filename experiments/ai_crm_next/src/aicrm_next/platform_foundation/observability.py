from __future__ import annotations


def health_payload() -> dict:
    return {"ok": True, "status": "ok", "service": "aicrm-next", "database": "fixture"}
