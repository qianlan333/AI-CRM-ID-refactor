from __future__ import annotations

import os

from aicrm_next.shared.errors import ContractError
from aicrm_next.shared.runtime import production_environment


COMMERCE_COUPONS_ENABLED_ENV = "AICRM_COMMERCE_COUPONS_ENABLED"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def commerce_coupons_new_activity_enabled() -> bool:
    """Allow local development while requiring an explicit production opt-in.

    This gate intentionally covers only actions that create new coupon state:
    claims and order reservations. Coupon reads, already-created order payment
    callbacks, reservation release, and reconciliation remain available while
    the production switch is off.
    """

    if not production_environment():
        return True
    value = str(os.getenv(COMMERCE_COUPONS_ENABLED_ENV, "") or "").strip().lower()
    return value in _TRUE_VALUES


def require_commerce_coupons_new_activity() -> None:
    if not commerce_coupons_new_activity_enabled():
        raise ContractError("coupon new activity is disabled")


__all__ = [
    "COMMERCE_COUPONS_ENABLED_ENV",
    "commerce_coupons_new_activity_enabled",
    "require_commerce_coupons_new_activity",
]
