from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from aicrm_next.commerce.domain import safe_completion_redirect_url
from aicrm_next.commerce.wechat_pay_client import WeChatPayClient, WeChatPayClientConfig, WeChatPayClientError
from aicrm_next.questionnaire.oauth import questionnaire_h5_identity_from_cookies
from aicrm_next.shared.runtime import production_data_ready, raw_database_url
from wecom_ability_service.infra.wechat_oauth import WeChatOAuthRequestError, exchange_wechat_oauth_code, fetch_wechat_userinfo

from .service import format_price, get_public_product, product_not_found_payload, route_headers


COOKIE_NAME = "wechat_pay_h5_identity"
STATE_TTL_SECONDS = 600


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _env(name: str, default: str = "") -> str:
    return _normalized_text(os.getenv(name, default))


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except (TypeError, ValueError):
        return int(default)


def _secret() -> str:
    return _env("AICRM_NEXT_ACTION_TOKEN_SECRET") or _env("SECRET_KEY") or "aicrm-next-h5-wechat-pay-dev-secret"


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(message: str) -> str:
    return hmac.new(_secret().encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_blob(payload: dict[str, Any]) -> str:
    encoded = _b64encode(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_sign(encoded)}"


def _load_signed_blob(value: str) -> dict[str, Any]:
    try:
        encoded, signature = value.split(".", 1)
    except ValueError:
        return {}
    if not hmac.compare_digest(_sign(encoded), signature):
        return {}
    try:
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_return_url(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized or not normalized.startswith("/") or normalized.startswith("//") or "\\" in normalized:
        return "/"
    return normalized


def _external_base_url(request: Request) -> str:
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    scheme = forwarded_proto or request.url.scheme or "http"
    host = forwarded_host or request.headers.get("Host") or request.url.netloc
    return f"{scheme}://{host}".rstrip("/")


def _oauth_configured() -> bool:
    return bool(_env("WECHAT_MP_APP_ID") and _env("WECHAT_MP_APP_SECRET") and _secret())


def _wechat_oauth_scope() -> str:
    return _env("WECHAT_PAY_OAUTH_SCOPE") or "snsapi_userinfo"


def _wechat_oauth_authorize_url(*, app_id: str, redirect_uri: str, scope: str, state: str) -> str:
    query = urlencode(
        {
            "appid": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope or "snsapi_base",
            "state": state,
        }
    )
    return f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"


def _is_wechat_browser(request: Request) -> bool:
    return "micromessenger" in (request.headers.get("User-Agent") or "").lower()


def _identity_from_request(request: Request) -> dict[str, str]:
    for cookie_name in (COOKIE_NAME,):
        payload = _load_signed_blob(_normalized_text(request.cookies.get(cookie_name)))
        openid = _normalized_text(payload.get("openid"))
        if openid:
            return {
                "openid": openid,
                "unionid": _normalized_text(payload.get("unionid")),
                "respondent_key": _normalized_text(payload.get("respondent_key")),
                "external_userid": _normalized_text(payload.get("external_userid")),
                "payer_name": _normalized_text(payload.get("payer_name")),
            }
    questionnaire_identity = questionnaire_h5_identity_from_cookies(request.cookies)
    openid = _normalized_text(questionnaire_identity.get("openid"))
    if openid:
        return {
            "openid": openid,
            "unionid": _normalized_text(questionnaire_identity.get("unionid")),
            "respondent_key": _normalized_text(questionnaire_identity.get("respondent_key")),
            "external_userid": _normalized_text(questionnaire_identity.get("external_userid")),
            "payer_name": "",
        }
    return {}


def payment_oauth_start_url(return_url: str) -> str:
    return f"/api/h5/wechat-pay/oauth/start?{urlencode({'return_url': _safe_return_url(return_url)})}"


def payment_oauth_start(request: Request) -> RedirectResponse | JSONResponse:
    if not _oauth_configured():
        return JSONResponse({"ok": False, "error": "wechat_pay_oauth_not_configured"}, status_code=501, headers=route_headers())
    return_url = _safe_return_url(request.query_params.get("return_url") or "/")
    now = int(datetime.now(timezone.utc).timestamp())
    state = _signed_blob({"return_url": return_url, "nonce": secrets.token_urlsafe(16), "iat": now, "exp": now + STATE_TTL_SECONDS})
    authorize_url = _wechat_oauth_authorize_url(
        app_id=_env("WECHAT_MP_APP_ID"),
        redirect_uri=f"{_external_base_url(request)}/api/h5/wechat-pay/oauth/callback",
        scope=_wechat_oauth_scope(),
        state=state,
    )
    return RedirectResponse(authorize_url, status_code=302, headers=route_headers())


def payment_oauth_callback(request: Request) -> RedirectResponse | JSONResponse:
    state_payload = _load_signed_blob(_normalized_text(request.query_params.get("state")))
    if not state_payload:
        return JSONResponse({"ok": False, "error": "state_invalid"}, status_code=400, headers=route_headers())
    if int(state_payload.get("exp") or 0) < int(datetime.now(timezone.utc).timestamp()):
        return JSONResponse({"ok": False, "error": "state_expired"}, status_code=400, headers=route_headers())
    code = _normalized_text(request.query_params.get("code"))
    if not code:
        return JSONResponse({"ok": False, "error": "code_required"}, status_code=400, headers=route_headers())
    try:
        oauth_payload = exchange_wechat_oauth_code(app_id=_env("WECHAT_MP_APP_ID"), app_secret=_env("WECHAT_MP_APP_SECRET"), code=code)
    except WeChatOAuthRequestError as exc:
        return JSONResponse({"ok": False, "error": str(exc) or "wechat_oauth_failed"}, status_code=502, headers=route_headers())
    if oauth_payload.get("errcode") not in (None, 0):
        return JSONResponse({"ok": False, "error": oauth_payload.get("errmsg") or "wechat_oauth_failed"}, status_code=502, headers=route_headers())
    openid = _normalized_text(oauth_payload.get("openid"))
    unionid = _normalized_text(oauth_payload.get("unionid"))
    payer_name = ""
    access_token = _normalized_text(oauth_payload.get("access_token"))
    if _wechat_oauth_scope() == "snsapi_userinfo" and access_token and openid:
        try:
            userinfo = fetch_wechat_userinfo(access_token=access_token, openid=openid)
            if userinfo.get("errcode") in (None, 0):
                unionid = unionid or _normalized_text(userinfo.get("unionid"))
                payer_name = _normalized_text(userinfo.get("nickname"))
        except WeChatOAuthRequestError:
            payer_name = ""
    response = RedirectResponse(_safe_return_url(state_payload.get("return_url")), status_code=302, headers=route_headers())
    response.set_cookie(
        COOKIE_NAME,
        _signed_blob({"openid": openid, "unionid": unionid, "payer_name": payer_name, "iat": int(datetime.now(timezone.utc).timestamp())}),
        max_age=86400 * 30,
        httponly=True,
        secure=_external_base_url(request).startswith("https://"),
        samesite="lax",
        path="/",
    )
    return response


def checkout_page_state(product: dict[str, Any], request: Request) -> dict[str, Any]:
    identity = _identity_from_request(request)
    code = _normalized_text(product.get("product_code"))
    return {
        "product": {
            "product_code": code,
            "name": _normalized_text(product.get("title") or product.get("name")),
            "amount_total": int(product.get("price_cents") or product.get("amount_total") or 0),
            "currency": _normalized_text(product.get("currency")) or "CNY",
        },
        "identity_ready": bool(identity.get("openid")),
        "oauth_start_url": payment_oauth_start_url(f"/pay/{code}"),
        "create_order_url": "/api/h5/wechat-pay/jsapi/orders",
        "status_url_template": "/api/h5/wechat-pay/orders/{out_trade_no}",
        "enabled": _env_bool("WECHAT_PAY_ENABLED", False),
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("buy_button_text")) or "确认支付",
        "completion_action": product.get("completion_action") or {"type": "default", "redirect_url": ""},
        "paid_order": None,
        "price_display": format_price(product),
    }


def _client_config() -> WeChatPayClientConfig:
    app_id = _env("WECHAT_PAY_APP_ID") or _env("WECHAT_MP_APP_ID")
    return WeChatPayClientConfig(
        app_id=app_id,
        mch_id=_env("WECHAT_PAY_MCH_ID"),
        api_v3_key=_env("WECHAT_PAY_API_V3_KEY"),
        private_key_path=_env("WECHAT_PAY_PRIVATE_KEY_PATH"),
        merchant_serial_no=_env("WECHAT_PAY_CERT_SERIAL_NO"),
        platform_public_key_path=_env("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH"),
        platform_serial_no=_env("WECHAT_PAY_PLATFORM_CERT_SERIAL_NO"),
        api_base=_env("WECHAT_PAY_API_BASE") or "https://api.mch.weixin.qq.com",
        timeout_seconds=_env_int("WECHAT_PAY_TIMEOUT_SECONDS", 10),
    )


def _require_payment_ready() -> WeChatPayClientConfig:
    if not _env_bool("WECHAT_PAY_ENABLED", False):
        raise RuntimeError("wechat_pay_disabled")
    config = _client_config()
    missing = [
        key
        for key, value in {
            "WECHAT_PAY_APP_ID/WECHAT_MP_APP_ID": config.app_id,
            "WECHAT_PAY_MCH_ID": config.mch_id,
            "WECHAT_PAY_PRIVATE_KEY_PATH": config.private_key_path,
            "WECHAT_PAY_CERT_SERIAL_NO": config.merchant_serial_no,
        }.items()
        if not _normalized_text(value)
    ]
    if missing:
        raise RuntimeError("missing WeChat Pay config: " + ", ".join(missing))
    if not production_data_ready():
        raise RuntimeError("production_database_required")
    return config


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(raw_database_url(), row_factory=dict_row)


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))


def _out_trade_no() -> str:
    return "WXP" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(6).upper()


def _expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_success_url(value: Any) -> str:
    normalized = _normalized_text(value)
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized
    if normalized.startswith(("https://", "http://")):
        return normalized
    return ""


def _order_payload(row: dict[str, Any]) -> dict[str, Any]:
    completion_url = safe_completion_redirect_url(row.get("completion_redirect_url"))
    completion_enabled = bool(row.get("completion_redirect_enabled")) and bool(completion_url)
    return {
        "out_trade_no": _normalized_text(row.get("out_trade_no")),
        "product_code": _normalized_text(row.get("product_code")),
        "product_name": _normalized_text(row.get("product_name")),
        "amount_total": int(row.get("amount_total") or 0),
        "currency": _normalized_text(row.get("currency")) or "CNY",
        "status": _normalized_text(row.get("status")),
        "trade_state": _normalized_text(row.get("trade_state")),
        "success_url": _safe_success_url(row.get("success_url")),
        "completion_redirect": {"enabled": completion_enabled, "url": completion_url if completion_enabled else ""},
        "completion_action": {"type": "redirect", "redirect_url": completion_url} if completion_enabled else {"type": "default", "redirect_url": ""},
    }


def _insert_order(conn: Any, *, product: dict[str, Any], identity: dict[str, str], mobile: str, out_trade_no: str) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no, order_source, client_order_ref, product_code, product_name, description,
            amount_total, currency, payer_openid, respondent_key, unionid, external_userid,
            mobile_snapshot, payer_name_snapshot, status, success_url, metadata_json,
            request_meta_json, expires_at, created_at, updated_at
        )
        VALUES (
            %s, 'h5_checkout', '', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            'created', %s, %s::jsonb, %s::jsonb, %s::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING *
        """,
        (
            out_trade_no,
            product["product_code"],
            product["title"],
            product.get("description") or product["title"],
            int(product.get("price_cents") or 0),
            product.get("currency") or "CNY",
            identity.get("openid") or "",
            identity.get("respondent_key") or "",
            identity.get("unionid") or "",
            identity.get("external_userid") or "",
            mobile,
            identity.get("payer_name") or "",
            _safe_success_url(product.get("completion_redirect_url")),
            _jsonb({"completion_redirect": product.get("completion_redirect") or {}}),
            _jsonb({}),
            _expires_at(),
        ),
    ).fetchone()
    return dict(row or {})


def _update_payment_request(conn: Any, out_trade_no: str, *, prepay_id: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE wechat_pay_orders
        SET prepay_id = %s,
            status = 'paying',
            request_payload_json = %s::jsonb,
            response_payload_json = %s::jsonb,
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = %s
        RETURNING *
        """,
        (prepay_id, _jsonb(request_payload), _jsonb(response_payload), out_trade_no),
    ).fetchone()
    return dict(row or {})


def _mark_order_failed(conn: Any, out_trade_no: str, error_message: str) -> None:
    conn.execute(
        "UPDATE wechat_pay_orders SET status = 'failed', last_error = %s, updated_at = CURRENT_TIMESTAMP WHERE out_trade_no = %s",
        (error_message[:500], out_trade_no),
    )


def _apply_transaction(conn: Any, transaction: dict[str, Any]) -> dict[str, Any]:
    trade_no = _normalized_text(transaction.get("out_trade_no"))
    trade_state = _normalized_text(transaction.get("trade_state"))
    status = "paid" if trade_state == "SUCCESS" else ("closed" if trade_state in {"CLOSED", "REVOKED"} else "paying")
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    payer = transaction.get("payer") if isinstance(transaction.get("payer"), dict) else {}
    previous = conn.execute("SELECT * FROM wechat_pay_orders WHERE out_trade_no = %s LIMIT 1", (trade_no,)).fetchone()
    was_paid = _normalized_text((previous or {}).get("status")) == "paid" or _normalized_text((previous or {}).get("trade_state")) == "SUCCESS"
    order = conn.execute(
        """
        UPDATE wechat_pay_orders
        SET status = %s,
            trade_state = %s,
            transaction_id = %s,
            bank_type = %s,
            payer_openid = COALESCE(NULLIF(%s, ''), payer_openid),
            payer_total = %s,
            paid_at = CASE WHEN %s = 'SUCCESS' THEN NULLIF(%s, '')::timestamptz ELSE paid_at END,
            notify_payload_json = %s::jsonb,
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = %s
        RETURNING *
        """,
        (
            status,
            trade_state,
            _normalized_text(transaction.get("transaction_id")),
            _normalized_text(transaction.get("bank_type")),
            _normalized_text(payer.get("openid")),
            int(amount.get("payer_total") or amount.get("total") or 0),
            trade_state,
            _normalized_text(transaction.get("success_time")),
            _jsonb(transaction),
            trade_no,
        ),
    ).fetchone()
    order_payload = dict(order or {})
    is_paid = _normalized_text(order_payload.get("status")) == "paid" or _normalized_text(order_payload.get("trade_state")) == "SUCCESS"
    if is_paid and not was_paid:
        try:
            from wecom_ability_service.domains.external_push import service as external_push_service

            external_push_service.enqueue_transaction_paid_event(order_payload)
        except Exception:
            pass
    return order_payload


def create_jsapi_order_response(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not _is_wechat_browser(request):
        return JSONResponse({"ok": False, "error": "please_open_in_wechat"}, status_code=403, headers=route_headers())
    product_code = _normalized_text(payload.get("product_code"))
    try:
        product = get_public_product(product_code)
    except Exception:
        return JSONResponse(product_not_found_payload(product_code), status_code=404, headers=route_headers())
    identity = _identity_from_request(request)
    if not identity.get("openid"):
        return JSONResponse(
            {"ok": False, "error": "openid_required", "oauth_start_url": payment_oauth_start_url(f"/pay/{product_code}")},
            status_code=401,
            headers=route_headers(),
        )
    try:
        config = _require_payment_ready()
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=503, headers=route_headers())
    mobile = _normalized_text(payload.get("mobile"))
    if product.get("require_mobile") and not mobile:
        return JSONResponse({"ok": False, "error": "mobile_required"}, status_code=400, headers=route_headers())
    out_trade_no = _out_trade_no()
    notify_url = _env("WECHAT_PAY_NOTIFY_URL") or f"{_external_base_url(request)}/api/h5/wechat-pay/notify"
    transaction_payload = {
        "appid": config.app_id,
        "mchid": config.mch_id,
        "description": _normalized_text(product.get("title"))[:127],
        "out_trade_no": out_trade_no,
        "notify_url": notify_url,
        "amount": {"total": int(product.get("price_cents") or 0), "currency": product.get("currency") or "CNY"},
        "payer": {"openid": identity["openid"]},
        "attach": json.dumps({"product_code": product["product_code"], "client_order_ref": _normalized_text(payload.get("client_order_ref"))}, ensure_ascii=False, separators=(",", ":"))[:128],
    }
    try:
        client = WeChatPayClient(config)
        with _connect() as conn:
            _insert_order(conn, product=product, identity=identity, mobile=mobile, out_trade_no=out_trade_no)
            response_payload = client.create_jsapi_transaction(transaction_payload)
            prepay_id = _normalized_text(response_payload.get("prepay_id"))
            if not prepay_id:
                raise WeChatPayClientError("missing prepay_id from WeChat Pay")
            order = _update_payment_request(conn, out_trade_no, prepay_id=prepay_id, request_payload=transaction_payload, response_payload=response_payload)
            pay_params = client.build_jsapi_pay_params(prepay_id)
            conn.commit()
        return JSONResponse({"ok": True, "order": _order_payload(order), "pay_params": pay_params}, headers=route_headers())
    except Exception as exc:
        try:
            with _connect() as conn:
                _mark_order_failed(conn, out_trade_no, str(exc))
                conn.commit()
        except Exception:
            pass
        return JSONResponse({"ok": False, "error": str(exc) or "create_wechat_pay_order_failed"}, status_code=502, headers=route_headers())


def order_status_response(out_trade_no: str, request: Request) -> JSONResponse:
    if not production_data_ready():
        return JSONResponse({"ok": False, "error": "production_database_required"}, status_code=503, headers=route_headers())
    trade_no = _normalized_text(out_trade_no)
    with _connect() as conn:
        order = conn.execute("SELECT * FROM wechat_pay_orders WHERE out_trade_no = %s LIMIT 1", (trade_no,)).fetchone()
        if not order:
            return JSONResponse({"ok": False, "error": "order_not_found"}, status_code=404, headers=route_headers())
        if _normalized_text(request.query_params.get("refresh")).lower() in {"1", "true", "yes", "on"}:
            try:
                transaction = WeChatPayClient(_client_config()).query_order_by_out_trade_no(trade_no)
                order = _apply_transaction(conn, transaction)
                conn.commit()
            except Exception:
                pass
    return JSONResponse({"ok": True, "order": _order_payload(dict(order))}, headers=route_headers())


async def notify_response(request: Request) -> JSONResponse:
    body = (await request.body()).decode("utf-8")
    try:
        transaction = WeChatPayClient(_client_config()).verify_and_decrypt_notification(body=body, headers=dict(request.headers))
        if not production_data_ready():
            raise RuntimeError("production_database_required")
        with _connect() as conn:
            _apply_transaction(conn, transaction)
            conn.commit()
        return JSONResponse({"code": "SUCCESS", "message": "成功"})
    except Exception as exc:
        return JSONResponse({"code": "FAIL", "message": str(exc)}, status_code=401)
