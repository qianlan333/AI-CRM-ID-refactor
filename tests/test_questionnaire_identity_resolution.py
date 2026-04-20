from __future__ import annotations

from flask import Flask

from wecom_ability_service.domains.questionnaire import service as questionnaire_service


def test_questionnaire_identity_resolution_prefers_unionid_then_openid_then_external_userid(monkeypatch):
    app = Flask(__name__)
    app.config["WECOM_CORP_ID"] = "ww-test"
    calls: list[tuple[str, str]] = []

    class FakeResolveExternalContactIdentityQuery:
        def __call__(self, dto):
            if dto.unionid:
                calls.append(("unionid", dto.unionid))
                return None
            if dto.openid:
                calls.append(("openid", dto.openid))
                return {"external_userid": "wm_ext_001", "openid": dto.openid}
            if dto.external_userid:
                calls.append(("external_userid", dto.external_userid))
                return {"external_userid": dto.external_userid}
            return None

    monkeypatch.setattr(
        questionnaire_service,
        "ResolveExternalContactIdentityQuery",
        FakeResolveExternalContactIdentityQuery,
    )

    with app.app_context():
        resolved = questionnaire_service.resolve_questionnaire_submit_identity(
            openid="openid-001",
            unionid="union-001",
            external_userid="wm_ext_001",
        )

    assert calls == [("unionid", "union-001"), ("openid", "openid-001")]
    assert resolved["external_userid"] == "wm_ext_001"
    assert resolved["matched_by"] == "openid"


def test_apply_questionnaire_mobile_binding_routes_through_application_command(monkeypatch):
    calls: dict[str, object] = {}

    class FakeBindExternalContactIdentityCommand:
        def __call__(self, dto):
            calls["bind_dto"] = dto
            return {"person_id": 101, "external_userid": dto.external_userid, "mobile": dto.mobile}

    class FakeResolvePersonIdentityQuery:
        def __call__(self, dto):
            calls["resolve_dto"] = dto
            return {"person_id": 101, "is_bound": True}

    monkeypatch.setattr(
        questionnaire_service,
        "BindExternalContactIdentityCommand",
        FakeBindExternalContactIdentityCommand,
    )
    monkeypatch.setattr(
        questionnaire_service,
        "ResolvePersonIdentityQuery",
        FakeResolvePersonIdentityQuery,
    )

    payload = questionnaire_service.apply_questionnaire_mobile_binding(
        {
            "id": 88,
            "mobile_snapshot": "13800138000",
            "external_userid": "wm_ext_questionnaire_001",
            "follow_user_userid": "sales_01",
        }
    )

    bind_dto = calls["bind_dto"]
    resolve_dto = calls["resolve_dto"]
    assert bind_dto.external_userid == "wm_ext_questionnaire_001"
    assert bind_dto.owner_userid == "sales_01"
    assert bind_dto.bind_by_userid == "questionnaire_submit"
    assert bind_dto.mobile == "13800138000"
    assert bind_dto.force_rebind is True
    assert resolve_dto.external_userid == "wm_ext_questionnaire_001"
    assert payload["bound"] is True
    assert payload["binding"]["person_id"] == 101
