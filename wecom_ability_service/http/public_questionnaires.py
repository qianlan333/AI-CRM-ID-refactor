from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for

from ..infra.wechat_oauth import WeChatOAuthRequestError, exchange_wechat_oauth_code
from ..services import (
    QuestionnaireAlreadySubmittedError,
    get_public_questionnaire_by_slug,
    has_questionnaire_submission,
    submit_questionnaire,
)
from .questionnaire_support import (
    _fetch_wechat_userinfo,
    _is_wechat_browser,
    _mask_identity_value,
    _questionnaire_logger,
    _questionnaire_public_path,
    _questionnaire_request_identity,
    _questionnaire_session_identity,
    _questionnaire_source_params,
    _questionnaire_submitted_path,
    _require_wechat_browser_api,
    _require_wechat_browser_page,
    _wechat_oauth_callback_url,
    _wechat_oauth_is_configured,
    _wechat_oauth_scope,
    _decode_oauth_state,
    _encode_oauth_state,
)


def questionnaire_h5_page(slug: str):
    wechat_gate = _require_wechat_browser_page()
    if wechat_gate is not None:
        return wechat_gate
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        abort(404)
    source_params = _questionnaire_source_params()
    session_identity = _questionnaire_session_identity()
    request_identity = _questionnaire_request_identity()
    if has_questionnaire_submission(int(questionnaire["id"]), request_identity):
        return redirect(_questionnaire_submitted_path(slug))
    is_wechat_browser = _is_wechat_browser()
    oauth_query = {"slug": slug, **source_params}
    oauth_start_url = f"{url_for('api.h5_wechat_oauth_start')}?{urlencode(oauth_query)}"
    page_mode = "questionnaire"
    env_notice = ""
    if is_wechat_browser and not session_identity.get("openid"):
        page_mode = "auth_gate"
        if _wechat_oauth_is_configured():
            env_notice = "授权后即可填写问卷信息。"
        else:
            env_notice = "当前为微信环境，但未配置公众号 OAuth，当前页面仅供测试。"
    page_state = {
        "slug": slug,
        "mode": page_mode,
        "api_url": f"/api/h5/questionnaires/{slug}",
        "submit_url": f"/api/h5/questionnaires/{slug}/submit",
        "submitted_url": _questionnaire_submitted_path(slug),
        "title": questionnaire.get("title", ""),
        "description": questionnaire.get("description", ""),
        "env_notice": env_notice,
        "oauth_start_url": oauth_start_url if _wechat_oauth_is_configured() else "",
        "is_wechat_browser": is_wechat_browser,
        "is_authorized": bool(session_identity.get("openid")),
    }
    return render_template(
        "questionnaire_h5_page.html",
        page_state=page_state,
    )


def questionnaire_h5_submitted(slug: str):
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        abort(404)
    return render_template("questionnaire_h5_submitted.html")


def public_get_questionnaire(slug: str):
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    if has_questionnaire_submission(int(questionnaire["id"]), _questionnaire_request_identity()):
        return jsonify({"ok": False, "error": "already_submitted", "message": "已经提交"}), 409
    return jsonify({"ok": True, "questionnaire": questionnaire})


def public_submit_questionnaire(slug: str):
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    payload = request.get_json(silent=True) or {}
    request_meta = {
        "ip": (request.headers.get("X-Forwarded-For", "").split(",")[0] or request.remote_addr or "").strip(),
        "user_agent": request.headers.get("User-Agent", ""),
    }
    try:
        result = submit_questionnaire(slug, payload, request_meta=request_meta)
        return jsonify(result)
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except QuestionnaireAlreadySubmittedError as exc:
        return jsonify({"success": False, "error": "already_submitted", "message": str(exc) or "已经提交"}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


def debug_questionnaire_session():
    if not current_app.config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API"):
        abort(404)
    return jsonify({"ok": True, "questionnaire_h5_identity": session.get("questionnaire_h5_identity") or {}})


def h5_wechat_oauth_start():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    slug = request.args.get("slug", "").strip()
    if not slug:
        return jsonify({"ok": False, "error": "slug is required"}), 400
    state = _encode_oauth_state({"slug": slug, **_questionnaire_source_params()})
    redirect_uri = _wechat_oauth_callback_url()
    _questionnaire_logger().info(
        "oauth start slug=%s source_channel=%s campaign_id=%s staff_id=%s redirect_uri=%s",
        slug,
        request.args.get("source_channel", "").strip(),
        request.args.get("campaign_id", "").strip(),
        request.args.get("staff_id", "").strip(),
        redirect_uri,
    )
    query = urlencode(
        {
            "appid": current_app.config["WECHAT_MP_APP_ID"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _wechat_oauth_scope(),
            "state": state,
        }
    )
    authorize_url = f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"
    return redirect(authorize_url)


def h5_wechat_oauth_callback():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    code = request.args.get("code", "").strip()
    state_payload = _decode_oauth_state(request.args.get("state", "").strip())
    slug = state_payload.get("slug", "").strip()
    if not code:
        _questionnaire_logger().warning("oauth callback failed reason=missing_code")
        return jsonify({"ok": False, "error": "code is required"}), 400
    if not slug:
        _questionnaire_logger().warning("oauth callback failed reason=invalid_state")
        return jsonify({"ok": False, "error": "invalid_state"}), 400

    try:
        oauth_payload = exchange_wechat_oauth_code(
            app_id=current_app.config["WECHAT_MP_APP_ID"],
            app_secret=current_app.config["WECHAT_MP_APP_SECRET"],
            code=code,
        )
    except WeChatOAuthRequestError as exc:
        _questionnaire_logger().exception("oauth callback failed slug=%s code=%s", slug, code)
        return jsonify({"ok": False, "error": f"wechat_oauth_exchange_failed: {exc}"}), 502

    if oauth_payload.get("errcode") not in (None, 0):
        _questionnaire_logger().warning(
            "oauth callback failed slug=%s code=%s wechat_payload=%s",
            slug,
            code,
            oauth_payload,
        )
        return jsonify({"ok": False, "error": "wechat_oauth_exchange_failed", "wechat_payload": oauth_payload}), 502

    openid = str(oauth_payload.get("openid") or "").strip()
    unionid = str(oauth_payload.get("unionid") or "").strip()
    access_token = str(oauth_payload.get("access_token") or "").strip()
    oauth_scope = _wechat_oauth_scope()
    if not unionid and oauth_scope == "snsapi_userinfo" and access_token and openid:
        try:
            userinfo_payload = _fetch_wechat_userinfo(access_token, openid)
        except WeChatOAuthRequestError:
            _questionnaire_logger().exception(
                "oauth callback userinfo fetch failed slug=%s openid=%s",
                slug,
                _mask_identity_value(openid),
            )
        else:
            if userinfo_payload.get("errcode") not in (None, 0):
                _questionnaire_logger().warning(
                    "oauth callback userinfo fetch failed slug=%s openid=%s wechat_payload=%s",
                    slug,
                    _mask_identity_value(openid),
                    userinfo_payload,
                )
            else:
                unionid = str(userinfo_payload.get("unionid") or "").strip()
    respondent_key = unionid or openid
    session["questionnaire_h5_identity"] = {
        "openid": openid,
        "unionid": unionid,
        "respondent_key": respondent_key,
        "oauth_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "slug": slug,
    }
    session.modified = True
    _questionnaire_logger().info(
        "oauth session written slug=%s respondent_key=%s openid=%s unionid=%s",
        slug,
        _mask_identity_value(respondent_key),
        _mask_identity_value(openid),
        _mask_identity_value(unionid),
    )
    _questionnaire_logger().info(
        "oauth callback success slug=%s openid=%s unionid=%s",
        slug,
        _mask_identity_value(openid),
        _mask_identity_value(unionid),
    )

    redirect_query = urlencode({key: value for key, value in state_payload.items() if key != "slug"})
    target = _questionnaire_public_path(slug)
    if redirect_query:
        target = f"{target}?{redirect_query}"
    return redirect(target, code=302)



def register_routes(bp):
    bp.route('/s/<slug>', methods=['GET'])(questionnaire_h5_page)
    bp.route('/s/<slug>/submitted', methods=['GET'])(questionnaire_h5_submitted)
    bp.route('/api/h5/questionnaires/<slug>', methods=['GET'])(public_get_questionnaire)
    bp.route('/api/h5/questionnaires/<slug>/submit', methods=['POST'])(public_submit_questionnaire)
    bp.route('/api/debug/questionnaire/session', methods=['GET'])(debug_questionnaire_session)
    bp.route('/api/h5/wechat/oauth/start', methods=['GET'])(h5_wechat_oauth_start)
    bp.route('/api/h5/wechat/oauth/callback', methods=['GET'])(h5_wechat_oauth_callback)
