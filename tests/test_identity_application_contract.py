from __future__ import annotations

from aicrm_next.identity_contact.application import (
    GetSidebarContactBindingStatusQuery,
    ResolvePersonIdentityQuery,
)
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest


def test_identity_resolution_query_uses_next_fixture_repository():
    result = ResolvePersonIdentityQuery().execute(ResolvePersonIdentityRequest(external_userid="wx_ext_001"))

    assert result is not None
    assert result.person_id == "person_001"
    assert result.mobile == "13800138000"
    assert result.owner_userid == "ZhaoYanFang"


def test_sidebar_contact_binding_status_query_is_next_owned():
    payload = GetSidebarContactBindingStatusQuery().execute(external_userid="wx_ext_001")

    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["source_status"] == "identity_contact"
    assert payload["is_bound"] is True
