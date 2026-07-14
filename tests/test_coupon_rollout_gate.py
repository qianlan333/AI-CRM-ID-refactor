from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aicrm_next.admin_shell.navigation import nav_items
from aicrm_next.commerce.coupons import application as coupon_application
from aicrm_next.commerce.coupons.application import CouponPublicApplication
from aicrm_next.shared.capability_flags import (
    COMMERCE_COUPONS_ENABLED_ENV,
    commerce_coupons_new_activity_enabled,
)
from aicrm_next.shared.errors import ContractError


_PRODUCTION_ENV_KEYS = ("AICRM_NEXT_ENV", "ENVIRONMENT", "APP_ENV", "FLASK_ENV")


def _local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PRODUCTION_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv(COMMERCE_COUPONS_ENABLED_ENV, raising=False)


def _production_environment(monkeypatch: pytest.MonkeyPatch, *, enabled: str | None = None) -> None:
    _local_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    if enabled is not None:
        monkeypatch.setenv(COMMERCE_COUPONS_ENABLED_ENV, enabled)


def _transaction_labels() -> list[str]:
    transaction = next(group for group in nav_items("") if group["title"] == "交易")
    return [str(item["label"]) for item in transaction["items"]]


def test_coupon_rollout_is_local_on_but_production_explicit_opt_in(monkeypatch) -> None:
    _local_environment(monkeypatch)
    assert commerce_coupons_new_activity_enabled() is True
    assert "优惠券" in _transaction_labels()

    _production_environment(monkeypatch)
    assert commerce_coupons_new_activity_enabled() is False
    assert "优惠券" not in _transaction_labels()

    monkeypatch.setenv(COMMERCE_COUPONS_ENABLED_ENV, "true")
    assert commerce_coupons_new_activity_enabled() is True
    assert "优惠券" in _transaction_labels()


class _PublicReadRepository:
    def __init__(self) -> None:
        self.claim_calls = 0
        self.available_calls = 0

    @staticmethod
    def resolve_canonical_unionid(_identity) -> str:
        return "union_coupon_rollout"

    @staticmethod
    def get_coupon_by_slug(_public_slug: str) -> dict:
        return {
            "id": 17,
            "public_slug": "rollout-coupon",
            "name": "灰度优惠券",
            "display_state": "active",
            "per_user_issue_limit": 2,
            "validity_mode": "fixed_range",
            "use_starts_at": datetime(2026, 7, 14, tzinfo=timezone.utc),
            "use_ends_at": datetime(2026, 7, 21, tzinfo=timezone.utc),
            "products": [],
        }

    @staticmethod
    def count_user_claims(_coupon_id: int, *, unionid: str) -> int:
        assert unionid == "union_coupon_rollout"
        return 1

    def list_available_claims(self, _target_ref: str, *, unionid: str, now) -> dict:
        assert unionid == "union_coupon_rollout"
        assert now.tzinfo is not None
        self.available_calls += 1
        return {"ok": True, "items": [], "total": 0}

    def claim_coupon(self, *_args, **_kwargs):
        self.claim_calls += 1
        raise AssertionError("disabled rollout must not write a claim")


def test_production_gate_keeps_coupon_reads_but_blocks_new_claims(monkeypatch) -> None:
    _production_environment(monkeypatch)
    repo = _PublicReadRepository()
    application = CouponPublicApplication(repository=repo)

    state = application.get_coupon(
        "rollout-coupon",
        identity={"openid": "openid_coupon_rollout"},
    )
    available = application.list_available_claims(
        "opaque-target-ref",
        identity={"openid": "openid_coupon_rollout"},
    )

    assert state["rollout_enabled"] is False
    assert state["claimable"] is False
    assert state["claimed"] is True
    assert available["ok"] is True
    assert available["items"] == []
    assert available["total"] == 0
    assert available["rollout_enabled"] is False
    assert repo.available_calls == 0

    with pytest.raises(ContractError, match="coupon new activity is disabled"):
        application.claim_coupon(
            "rollout-coupon",
            identity={"openid": "openid_coupon_rollout"},
            idempotency_key="claim-rollout-disabled",
        )
    assert repo.claim_calls == 0


class _ExistingOrderCouponRepository:
    def __init__(self) -> None:
        self.events: list[str] = []

    def reserve_coupon_for_order(self, **_kwargs):
        self.events.append("reserve")
        raise AssertionError("disabled rollout must not reserve a coupon")

    def consume_coupon_for_paid_order(self, **_kwargs):
        self.events.append("consume")
        return {"ok": True, "status": "consumed"}

    def release_coupon_for_order(self, **_kwargs):
        self.events.append("release")
        return {"ok": True, "status": "released"}


def test_production_gate_blocks_only_new_reservations_not_existing_order_completion(
    monkeypatch,
) -> None:
    _production_environment(monkeypatch)
    repository = _ExistingOrderCouponRepository()
    monkeypatch.setattr(
        coupon_application,
        "build_coupon_order_repository",
        lambda _conn: repository,
    )
    order = {
        "id": 91,
        "out_trade_no": "WXP_ROLLOUT_GATE",
        "amount_total": 10_000,
        "currency": "CNY",
    }

    no_coupon_order = coupon_application.reserve_coupon_for_order(
        object(),
        order=order,
        coupon_choice={"mode": "none"},
        unionid="union_coupon_rollout",
        trade_product_id=7,
    )
    assert no_coupon_order["amount_total"] == 10_000
    assert no_coupon_order["coupon_claim_id"] is None

    with pytest.raises(ContractError, match="coupon new activity is disabled"):
        coupon_application.reserve_coupon_for_order(
            object(),
            order=order,
            coupon_choice={"mode": "auto"},
            unionid="union_coupon_rollout",
            trade_product_id=7,
        )

    consumed = coupon_application.consume_coupon_for_paid_order(
        object(),
        out_trade_no="WXP_ROLLOUT_GATE",
        provider_total=8_000,
        provider_currency="CNY",
    )
    released = coupon_application.release_coupon_for_order(
        object(),
        out_trade_no="WXP_ROLLOUT_RELEASE",
        reason="order_closed",
    )

    assert consumed["status"] == "consumed"
    assert released["status"] == "released"
    assert repository.events == ["consume", "release"]


def test_disabled_rollout_public_page_uses_explicit_unavailable_copy() -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "aicrm_next/commerce/coupons/templates/coupon_public.html"
    ).read_text(encoding="utf-8")

    assert "state.rollout_enabled is sameas false" in template
    assert "优惠券暂未开放" in template
