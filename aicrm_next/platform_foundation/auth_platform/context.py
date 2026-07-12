from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class PrincipalType(StrEnum):
    USER = "user"
    SERVICE = "service"
    AGENT = "agent"
    PARTNER = "partner"


def _normalized_values(values: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value or "").strip() for value in values if str(value or "").strip()}))


@dataclass(frozen=True)
class AuthContext:
    principal_type: PrincipalType
    sub: str
    client_id: str
    tenant_id: str
    audience: str
    scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    token_id: str
    expires_at: datetime
    auth_time: datetime
    actor: str = ""
    acr: str = ""
    resource_constraints: Mapping[str, Any] = field(default_factory=dict)
    sender_constraint: str = ""

    def __post_init__(self) -> None:
        required = {
            "sub": self.sub,
            "client_id": self.client_id,
            "tenant_id": self.tenant_id,
            "audience": self.audience,
            "token_id": self.token_id,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError(f"auth context missing required values: {','.join(missing)}")
        expires_at = _aware_utc(self.expires_at, "expires_at")
        auth_time = _aware_utc(self.auth_time, "auth_time")
        if expires_at <= auth_time:
            raise ValueError("auth context expiry must be after auth_time")
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "auth_time", auth_time)
        object.__setattr__(self, "scopes", _normalized_values(self.scopes))
        object.__setattr__(self, "capabilities", _normalized_values(self.capabilities))
        object.__setattr__(self, "resource_constraints", MappingProxyType(dict(self.resource_constraints)))

    def active(self, *, now: datetime | None = None) -> bool:
        current = _aware_utc(now or datetime.now(timezone.utc), "now")
        return current < self.expires_at

    def permits(
        self,
        *,
        audience: str,
        capability: str,
        scope: str = "",
        resource: Mapping[str, Any] | None = None,
    ) -> bool:
        if not self.active() or self.audience != str(audience or "").strip():
            return False
        if str(capability or "").strip() not in self.capabilities:
            return False
        if scope and str(scope).strip() not in self.scopes:
            return False
        requested = dict(resource or {})
        if not self.resource_constraints:
            return True
        return all(key in requested and _constraint_allows(allowed, requested[key]) for key, allowed in self.resource_constraints.items())


def _constraint_allows(allowed: Any, requested: Any) -> bool:
    if isinstance(allowed, (list, tuple, set, frozenset)):
        return requested in allowed
    return allowed == requested


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
