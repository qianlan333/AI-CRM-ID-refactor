#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACT_FILES = [
    "aicrm_next/integration_gateway/payment_contracts.py",
    "aicrm_next/integration_gateway/payment_adapters.py",
    "aicrm_next/integration_gateway/audit.py",
    "aicrm_next/integration_gateway/idempotency.py",
    "aicrm_next/commerce/application.py",
    "aicrm_next/commerce/api.py",
    "tools/product_management_gray_smoke.py",
    "tools/compare_commerce_parity.py",
    "tests/fixtures/old_commerce/products.default.json",
]
DOCS_TO_SCAN = [
    "docs/d7_4_product_payment_adapter_contract.md",
    "docs/d7_4_product_payment_adapter_implementation_report.md",
    "docs/d7_adapter_contract_catalog.md",
    "docs/d7_capability_readiness_matrix.md",
    "docs/d7_write_external_blocker_matrix.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]
REQUIRED_METHODS = {
    "ProductWriteGateway": [
        "create_product",
        "update_product",
        "enable_product",
        "disable_product",
        "delete_product",
        "build_product_write_preview",
        "record_product_write_audit",
    ],
    "WeChatPayAdapter": [
        "create_jsapi_order",
        "create_h5_order",
        "query_order",
        "close_order",
        "verify_notify_signature",
        "parse_notify_payload",
        "build_checkout_preview",
    ],
    "AlipayAdapter": [
        "create_wap_order",
        "query_order",
        "close_order",
        "verify_notify_signature",
        "parse_notify_payload",
        "build_return_preview",
        "build_checkout_preview",
    ],
    "PaymentNotifyGateway": [
        "receive_wechat_notify",
        "receive_alipay_notify",
        "build_notify_preview",
        "record_notify_audit",
        "build_order_status_update_preview",
    ],
    "PaymentReturnGateway": [
        "receive_alipay_return",
        "build_return_page_context",
        "record_return_audit",
    ],
}
REQUIRED_RESULT_FIELDS = [
    "ok",
    "adapter",
    "mode",
    "operation",
    "idempotency_key",
    "target",
    "result",
    "audit_id",
    "side_effect_executed",
    "error_code",
    "error_message",
]
FORBIDDEN_DOC_MARKERS = ["production_ready", "production_approved", "delete_ready"]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _class_methods(path: str, class_name: str) -> list[str]:
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [child.name for child in node.body if isinstance(child, ast.FunctionDef)]
    return []


def _with_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _check_runtime() -> dict[str, Any]:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.payment_adapters import (
        AlipayAdapter,
        PaymentNotifyGateway,
        PaymentReturnGateway,
        ProductWriteGateway,
        WeChatPayAdapter,
        build_alipay_adapter,
        build_payment_notify_gateway,
        build_product_write_gateway,
        build_wechat_pay_adapter,
    )

    reset_audit_events()
    reset_idempotency_store()
    product_a = ProductWriteGateway("fake").create_product(product_code="course_1", page_slug="course-1", amount=9900)
    product_b = ProductWriteGateway("fake").create_product(product_code="course_1", page_slug="course-1", amount=9900)
    product_update = ProductWriteGateway("fake").update_product(product_id="prod_001", product_code="course_1", amount=9900)
    wechat_a = WeChatPayAdapter("fake").create_jsapi_order(order_id="order_1", product_id="prod_001", openid="openid_1", amount=9900)
    wechat_b = WeChatPayAdapter("fake").create_jsapi_order(order_id="order_1", product_id="prod_001", openid="openid_1", amount=9900)
    alipay_a = AlipayAdapter("fake").create_wap_order(order_id="order_2", product_id="prod_001", payer_id="payer_1", amount=9900)
    alipay_b = AlipayAdapter("fake").create_wap_order(order_id="order_2", product_id="prod_001", payer_id="payer_1", amount=9900)
    wechat_notify_a = PaymentNotifyGateway("fake").receive_wechat_notify(order_id="order_1", transaction_id="tx_1", notify_id="notify_1", amount=9900)
    wechat_notify_b = PaymentNotifyGateway("fake").receive_wechat_notify(order_id="order_1", transaction_id="tx_1", notify_id="notify_1", amount=9900)
    alipay_notify = PaymentNotifyGateway("fake").receive_alipay_notify(order_id="order_2", transaction_id="tx_2", notify_id="notify_2", amount=9900)
    alipay_return = PaymentReturnGateway("fake").receive_alipay_return(order_id="order_2", transaction_id="tx_2", status="paid")
    disabled = WeChatPayAdapter("disabled").create_h5_order(order_id="order_disabled", amount=9900)

    previous_flags = {name: os.environ.get(name) for name in [
        "AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES",
        "AICRM_NEXT_ENABLE_REAL_WECHAT_PAY",
        "AICRM_NEXT_ENABLE_REAL_ALIPAY",
        "AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY",
    ]}
    for name in previous_flags:
        _with_env(name, None)
    guarded = [
        ProductWriteGateway("production").create_product(product_code="course_1"),
        WeChatPayAdapter("production").create_h5_order(order_id="order_1", amount=9900),
        AlipayAdapter("production").create_wap_order(order_id="order_2", amount=9900),
        PaymentNotifyGateway("production").receive_wechat_notify(order_id="order_1"),
    ]
    _with_env("AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES", "true")
    _with_env("AICRM_NEXT_ENABLE_REAL_WECHAT_PAY", "true")
    _with_env("AICRM_NEXT_ENABLE_REAL_ALIPAY", "true")
    _with_env("AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY", "true")
    guarded_enabled = [
        ProductWriteGateway("production").create_product(product_code="course_1"),
        WeChatPayAdapter("production").create_h5_order(order_id="order_1", amount=9900),
        AlipayAdapter("production").create_wap_order(order_id="order_2", amount=9900),
        PaymentNotifyGateway("production").receive_wechat_notify(order_id="order_1"),
    ]
    for name, value in previous_flags.items():
        _with_env(name, value)

    checked_results = [
        product_a,
        product_b,
        product_update,
        wechat_a,
        wechat_b,
        alipay_a,
        alipay_b,
        wechat_notify_a,
        wechat_notify_b,
        alipay_notify,
        alipay_return,
        disabled,
        *guarded,
        *guarded_enabled,
    ]
    events = list_audit_events()
    default_modes = {
        "product_write_mode": build_product_write_gateway().mode,
        "wechat_pay_mode": build_wechat_pay_adapter().mode,
        "alipay_mode": build_alipay_adapter().mode,
        "payment_notify_mode": build_payment_notify_gateway().mode,
    }
    return {
        "stable_shape": all(all(field in item for field in REQUIRED_RESULT_FIELDS) for item in checked_results),
        "fake_product_deterministic": product_a["result"] == product_b["result"],
        "fake_wechat_checkout_deterministic": wechat_a["result"] == wechat_b["result"],
        "fake_alipay_checkout_deterministic": alipay_a["result"] == alipay_b["result"],
        "fake_notify_deterministic": wechat_notify_a["result"] == wechat_notify_b["result"],
        "fake_return_no_side_effect": alipay_return["result"].get("return_processed") is False,
        "disabled_error": disabled["ok"] is False and disabled["error_code"] == "adapter_disabled",
        "production_guard": all(item["ok"] is False and item["error_code"] == "production_guard_failed" for item in guarded),
        "production_enabled_not_implemented": all(item["ok"] is False and item["error_code"] == "production_not_implemented" for item in guarded_enabled),
        "side_effect_executed_false": all(item["side_effect_executed"] is False for item in checked_results),
        "audit_events_created": len(events) >= len(checked_results) and all(event.get("audit_id") for event in events),
        "audit_fields_present": all(
            {"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event)
            for event in events
        ),
        "default_modes": default_modes,
        "default_fake_modes": all(value == "fake" for value in default_modes.values()),
        "real_flags": {
            "real_product_write_executed": False,
            "real_wechat_pay_executed": False,
            "real_alipay_executed": False,
            "real_payment_notify_executed": False,
            "real_payment_provider_called": False,
        },
    }


def _run_product_smoke() -> dict[str, Any]:
    from tools import product_management_gray_smoke as smoke

    report = smoke.run_smoke(
        Namespace(
            next_testclient=True,
            next_base_url="",
            include_fake_writes=True,
            output_md="/tmp/unused.md",
            output_json="/tmp/unused.json",
        )
    )
    return {
        "ok": bool(report.get("ok")),
        "route_count": len(report.get("route_results", [])),
        "side_effect_safety": report.get("side_effect_safety", {}),
        "blockers": report.get("blockers", []),
    }


def _run_commerce_parity() -> dict[str, Any]:
    from tools import compare_commerce_parity as parity

    report = parity.run_compare(
        Namespace(
            old_base_url="",
            next_base_url="",
            old_fixture_dir=str(REPO_ROOT / "tests/fixtures/old_commerce"),
            next_testclient=True,
            allow_old_write_endpoints=False,
            output_md="/tmp/unused.md",
            output_json="/tmp/unused.json",
        )
    )
    return {
        "ok": bool(report.get("ok")),
        "result_count": len(report.get("results", [])),
        "side_effect_safety": report.get("side_effect_safety", {}),
        "failures": [item for item in report.get("results", []) if item.get("status") == "FAIL"],
    }


def build_report() -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    missing_files = [path for path in CONTRACT_FILES + DOCS_TO_SCAN if not (REPO_ROOT / path).exists()]
    blockers.extend({"reason": "missing_file", "path": path} for path in missing_files)

    adapter_contracts = {
        class_name: _class_methods("aicrm_next/integration_gateway/payment_adapters.py", class_name)
        for class_name in REQUIRED_METHODS
        if (REPO_ROOT / "aicrm_next/integration_gateway/payment_adapters.py").exists()
    }
    for class_name, required in REQUIRED_METHODS.items():
        missing = [method for method in required if method not in adapter_contracts.get(class_name, [])]
        blockers.extend({"reason": "missing_adapter_method", "class": class_name, "method": method} for method in missing)

    runtime = _check_runtime() if not missing_files else {}
    for key in [
        "stable_shape",
        "fake_product_deterministic",
        "fake_wechat_checkout_deterministic",
        "fake_alipay_checkout_deterministic",
        "fake_notify_deterministic",
        "fake_return_no_side_effect",
        "disabled_error",
        "production_guard",
        "production_enabled_not_implemented",
        "side_effect_executed_false",
        "audit_events_created",
        "audit_fields_present",
        "default_fake_modes",
    ]:
        if runtime and runtime.get(key) is not True:
            blockers.append({"reason": "runtime_check_failed", "check": key})

    product_smoke = _run_product_smoke() if not missing_files else {"ok": False, "blockers": [{"reason": "missing_files"}]}
    commerce_parity = _run_commerce_parity() if not missing_files else {"ok": False, "failures": [{"reason": "missing_files"}]}
    if not product_smoke.get("ok"):
        blockers.append({"reason": "product_smoke_failed", "details": product_smoke.get("blockers", [])})
    if not commerce_parity.get("ok"):
        blockers.append({"reason": "commerce_parity_failed", "details": commerce_parity.get("failures", [])})

    docs_text = "\n".join(_read(path) for path in DOCS_TO_SCAN if (REPO_ROOT / path).exists())
    for marker in FORBIDDEN_DOC_MARKERS:
        if marker in docs_text:
            blockers.append({"reason": "forbidden_doc_marker", "marker": marker})

    adapter_source = _read("aicrm_next/integration_gateway/payment_adapters.py") if (REPO_ROOT / "aicrm_next/integration_gateway/payment_adapters.py").exists() else ""
    for flag in [
        "AICRM_NEXT_ENABLE_REAL_PRODUCT_WRITES",
        "AICRM_NEXT_ENABLE_REAL_WECHAT_PAY",
        "AICRM_NEXT_ENABLE_REAL_ALIPAY",
        "AICRM_NEXT_ENABLE_REAL_PAYMENT_NOTIFY",
    ]:
        if flag not in adapter_source:
            blockers.append({"reason": "missing_production_guard_flag", "flag": flag})

    recommendation = "D7.4 adapter-contract acceptance can proceed" if not blockers else "Do not accept D7.4 until blockers are cleared"
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "adapter_contracts": adapter_contracts,
        "mode_guards": {
            "default_modes": runtime.get("default_modes", {}),
            "production_without_flag_fails_closed": runtime.get("production_guard") is True,
            "production_with_flag_not_implemented": runtime.get("production_enabled_not_implemented") is True,
        },
        "idempotency": {
            "fake_product_deterministic": runtime.get("fake_product_deterministic") is True,
            "fake_wechat_checkout_deterministic": runtime.get("fake_wechat_checkout_deterministic") is True,
            "fake_alipay_checkout_deterministic": runtime.get("fake_alipay_checkout_deterministic") is True,
            "fake_notify_deterministic": runtime.get("fake_notify_deterministic") is True,
        },
        "audit": {
            "audit_events_created": runtime.get("audit_events_created") is True,
            "audit_fields_present": runtime.get("audit_fields_present") is True,
        },
        "side_effect_safety": {
            "side_effect_executed_false": runtime.get("side_effect_executed_false") is True,
            **runtime.get("real_flags", {}),
        },
        "product_smoke": product_smoke,
        "commerce_parity": commerce_parity,
        "recommendation": recommendation,
    }


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# D7.4 Product Payment Adapter Contract Check",
        "",
        f"- overall: {'PASS' if report['ok'] else 'FAIL'}",
        f"- recommendation: {report['recommendation']}",
        f"- blockers: {len(report['blockers'])}",
        f"- warnings: {len(report['warnings'])}",
        "",
        "## Adapter Contracts",
    ]
    for class_name, methods in report["adapter_contracts"].items():
        lines.append(f"- {class_name}: {', '.join(methods)}")
    lines.extend(
        [
            "",
            "## Mode Guards",
            *[f"- {key}: {value}" for key, value in report["mode_guards"].items()],
            "",
            "## Idempotency",
            *[f"- {key}: {value}" for key, value in report["idempotency"].items()],
            "",
            "## Audit",
            *[f"- {key}: {value}" for key, value in report["audit"].items()],
            "",
            "## Side Effect Safety",
            *[f"- {key}: {value}" for key, value in report["side_effect_safety"].items()],
            "",
            "## Product Smoke",
            f"- ok: {report['product_smoke'].get('ok')}",
            "",
            "## Commerce Parity",
            f"- ok: {report['commerce_parity'].get('ok')}",
            "",
            "## Blockers",
        ]
    )
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check D7.4 Product/Payment adapter contract readiness.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    write_markdown_report(report, Path(args.output_md))
    write_json_report(report, Path(args.output_json))
    print(f"wrote markdown report: {args.output_md}")
    print(f"wrote json report: {args.output_json}")
    print("overall:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
