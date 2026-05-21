from __future__ import annotations

LEGACY_COMPATIBILITY_SHIM = True

from legacy_flask.legacy_lockdown import (  # noqa: F401
    ALLOWED_FALLBACK_RULES,
    RETIRED_ROUTE_RULES,
    AllowedFallbackRule,
    RetiredRouteRule,
    load_lockdown_rules,
    match_allowed_fallback_route,
    match_retired_route,
    register_legacy_lockdown,
)

__all__ = [
    "ALLOWED_FALLBACK_RULES",
    "LEGACY_COMPATIBILITY_SHIM",
    "RETIRED_ROUTE_RULES",
    "AllowedFallbackRule",
    "RetiredRouteRule",
    "load_lockdown_rules",
    "match_allowed_fallback_route",
    "match_retired_route",
    "register_legacy_lockdown",
]
