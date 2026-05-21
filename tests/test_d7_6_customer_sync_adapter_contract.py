from __future__ import annotations

import importlib
from argparse import Namespace
from pathlib import Path

from aicrm_next.customer_read_model.application import (
    GetCustomerChatContextQuery,
    ListCustomersQuery,
    ListRecentMessagesQuery,
)
from aicrm_next.customer_read_model.dto import CustomerChatContextRequest, ListCustomersRequest, RecentMessagesRequest
from aicrm_next.customer_read_model.repo import FixtureCustomerReadRepository
from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery, UpsertIdentityMappingCommand
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.identity_contact.repo import FixtureIdentityRepository
from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
from aicrm_next.integration_gateway.customer_sync_adapters import (
    ArchiveSyncAdapter,
    ContactsSyncAdapter,
    CustomerProjectionSyncGateway,
    IdentityMappingAdapter,
)
from aicrm_next.integration_gateway.idempotency import reset_idempotency_store

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_d7_6_files_exist() -> None:
    for relpath in [
        "aicrm_next/integration_gateway/customer_sync_contracts.py",
        "aicrm_next/integration_gateway/customer_sync_adapters.py",
        "docs/d7_6_archive_contacts_identity_adapter_contract.md",
        "docs/d7_6_archive_contacts_identity_adapter_implementation_report.md",
        "tools/check_d7_6_customer_sync_adapter_contract.py",
        "tools/customer_read_model_gray_smoke.py",
        "tools/compare_customer_read_model_parity.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists(), relpath


def test_adapter_contract_classes_and_methods_exist() -> None:
    contracts = importlib.import_module("aicrm_next.integration_gateway.customer_sync_contracts")
    adapters = importlib.import_module("aicrm_next.integration_gateway.customer_sync_adapters")
    required = {
        "ArchiveSyncAdapter": ["fetch_recent_messages", "fetch_incremental_archive_messages", "normalize_archive_message", "build_archive_sync_preview", "record_archive_sync_audit"],
        "ContactsSyncAdapter": ["fetch_external_contacts", "fetch_contact_detail", "fetch_follow_user_relations", "build_contacts_sync_preview", "record_contacts_sync_audit"],
        "IdentityMappingAdapter": ["resolve_person_identity", "upsert_identity_mapping", "link_openid_unionid_external_userid", "build_identity_mapping_preview", "record_identity_mapping_audit"],
        "CustomerProjectionSyncGateway": ["update_customer_list_projection", "update_customer_detail_projection", "update_customer_timeline_projection", "update_recent_messages_projection", "build_projection_sync_preview", "record_projection_sync_audit"],
    }
    for class_name, methods in required.items():
        assert hasattr(contracts, f"{class_name}Contract")
        cls = getattr(adapters, class_name)
        for method in methods:
            assert callable(getattr(cls, method))


def _assert_result_shape(result: dict) -> None:
    assert {
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
    } <= set(result)
    assert result["side_effect_executed"] is False


def test_fake_adapter_operations_are_deterministic_with_idempotency_key() -> None:
    reset_audit_events()
    reset_idempotency_store()
    operations = [
        (
            ArchiveSyncAdapter("fake"),
            lambda adapter, key: adapter.fetch_recent_messages(external_userid="wx_ext_001", idempotency_key=key),
        ),
        (
            ArchiveSyncAdapter("fake"),
            lambda adapter, key: adapter.fetch_incremental_archive_messages(sync_cursor="cursor_001", idempotency_key=key),
        ),
        (
            ContactsSyncAdapter("fake"),
            lambda adapter, key: adapter.fetch_external_contacts(follow_user_userid="ZhaoYanFang", idempotency_key=key),
        ),
        (
            IdentityMappingAdapter("fake"),
            lambda adapter, key: adapter.resolve_person_identity(external_userid="wx_ext_001", idempotency_key=key),
        ),
        (
            CustomerProjectionSyncGateway("fake"),
            lambda adapter, key: adapter.update_recent_messages_projection(external_userid="wx_ext_001", idempotency_key=key),
        ),
    ]
    for index, (adapter, call) in enumerate(operations):
        first = call(adapter, f"same-key-{index}")
        second = call(adapter, f"same-key-{index}")
        _assert_result_shape(first)
        assert first["result"] == second["result"]
        assert first["side_effect_executed"] is False


def test_disabled_and_production_modes_fail_closed(monkeypatch) -> None:
    cases = [
        (ArchiveSyncAdapter, "AICRM_NEXT_ENABLE_REAL_ARCHIVE_SYNC", lambda adapter: adapter.fetch_recent_messages(external_userid="wx_ext_001")),
        (ContactsSyncAdapter, "AICRM_NEXT_ENABLE_REAL_CONTACTS_SYNC", lambda adapter: adapter.fetch_contact_detail(external_userid="wx_ext_001")),
        (IdentityMappingAdapter, "AICRM_NEXT_ENABLE_REAL_IDENTITY_MAPPING", lambda adapter: adapter.upsert_identity_mapping(external_userid="wx_ext_001")),
        (CustomerProjectionSyncGateway, "AICRM_NEXT_ENABLE_REAL_CUSTOMER_PROJECTION_SYNC", lambda adapter: adapter.update_customer_list_projection()),
    ]
    for cls, flag, call in cases:
        disabled = call(cls("disabled"))
        assert disabled["ok"] is False
        assert disabled["error_code"] == "adapter_disabled"
        assert disabled["side_effect_executed"] is False

        monkeypatch.delenv(flag, raising=False)
        guarded = call(cls("production"))
        assert guarded["ok"] is False
        assert guarded["error_code"] == "production_guard_failed"
        assert guarded["side_effect_executed"] is False

        monkeypatch.setenv(flag, "true")
        still_closed = call(cls("production"))
        assert still_closed["ok"] is False
        assert still_closed["error_code"] == "production_not_implemented"
        assert still_closed["side_effect_executed"] is False
        monkeypatch.delenv(flag, raising=False)


def test_staging_mode_has_no_side_effects() -> None:
    results = [
        ArchiveSyncAdapter("staging").fetch_recent_messages(external_userid="wx_ext_001"),
        ContactsSyncAdapter("staging").fetch_contact_detail(external_userid="wx_ext_001"),
        IdentityMappingAdapter("staging").link_openid_unionid_external_userid(external_userid="wx_ext_001", openid="openid_001"),
        CustomerProjectionSyncGateway("staging").update_customer_detail_projection(external_userid="wx_ext_001"),
    ]
    for result in results:
        assert result["ok"] is True
        assert result["mode"] == "staging"
        assert result["side_effect_executed"] is False
        assert not any(result["result"]["side_effect_safety"].values())


def test_audit_record_created_for_each_adapter_family() -> None:
    reset_audit_events()
    reset_idempotency_store()
    ArchiveSyncAdapter("fake").fetch_recent_messages(external_userid="wx_ext_001")
    ContactsSyncAdapter("fake").fetch_contact_detail(external_userid="wx_ext_001")
    IdentityMappingAdapter("fake").upsert_identity_mapping(external_userid="wx_ext_001", openid="openid_001")
    CustomerProjectionSyncGateway("fake").update_recent_messages_projection(external_userid="wx_ext_001")
    events = list_audit_events()
    adapters = {event["adapter"] for event in events}
    assert {"ArchiveSyncAdapter", "ContactsSyncAdapter", "IdentityMappingAdapter", "CustomerProjectionSyncGateway"} <= adapters
    assert all(event["side_effect_executed"] is False for event in events)
    assert all({"audit_id", "adapter", "operation", "mode", "idempotency_key", "side_effect_executed", "status", "error_code", "created_at"} <= set(event) for event in events)


class SpyArchiveSyncAdapter(ArchiveSyncAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def fetch_recent_messages(self, **kwargs):
        self.calls.append("fetch_recent_messages")
        return super().fetch_recent_messages(**kwargs)


class SpyContactsSyncAdapter(ContactsSyncAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def fetch_external_contacts(self, **kwargs):
        self.calls.append("fetch_external_contacts")
        return super().fetch_external_contacts(**kwargs)


class SpyIdentityMappingAdapter(IdentityMappingAdapter):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def resolve_person_identity(self, **kwargs):
        self.calls.append("resolve_person_identity")
        return super().resolve_person_identity(**kwargs)

    def upsert_identity_mapping(self, **kwargs):
        self.calls.append("upsert_identity_mapping")
        return super().upsert_identity_mapping(**kwargs)


class SpyProjectionSyncGateway(CustomerProjectionSyncGateway):
    def __init__(self) -> None:
        super().__init__("fake")
        self.calls: list[str] = []

    def update_customer_list_projection(self, **kwargs):
        self.calls.append("update_customer_list_projection")
        return super().update_customer_list_projection(**kwargs)

    def update_recent_messages_projection(self, **kwargs):
        self.calls.append("update_recent_messages_projection")
        return super().update_recent_messages_projection(**kwargs)


def test_customer_recent_messages_uses_archive_and_projection_boundaries() -> None:
    archive = SpyArchiveSyncAdapter()
    projection = SpyProjectionSyncGateway()
    result = ListRecentMessagesQuery(
        repo=FixtureCustomerReadRepository(),
        archive_adapter=archive,
        projection_gateway=projection,
    )(RecentMessagesRequest(external_userid="wx_ext_001", limit=2))
    assert archive.calls == ["fetch_recent_messages"]
    assert projection.calls == ["update_recent_messages_projection"]
    assert result["adapter_contract"]["archive_sync"]["adapter"] == "ArchiveSyncAdapter"
    assert result["adapter_contract"]["customer_projection"]["side_effect_executed"] is False
    assert result["messages"]


def test_customer_contact_sync_and_projection_boundaries_are_used() -> None:
    contacts = SpyContactsSyncAdapter()
    projection = SpyProjectionSyncGateway()
    result = ListCustomersQuery(
        repo=FixtureCustomerReadRepository(),
        contacts_adapter=contacts,
        projection_gateway=projection,
    )(ListCustomersRequest(limit=5, offset=0))
    assert contacts.calls == ["fetch_external_contacts"]
    assert projection.calls == ["update_customer_list_projection"]
    assert result["adapter_contract"]["contacts_sync"]["adapter"] == "ContactsSyncAdapter"
    assert result["adapter_contract"]["customer_projection"]["side_effect_executed"] is False


def test_identity_resolve_and_upsert_use_identity_mapping_boundary() -> None:
    identity = SpyIdentityMappingAdapter()
    resolved = ResolvePersonIdentityQuery(repo=FixtureIdentityRepository(), identity_adapter=identity)(
        ResolvePersonIdentityRequest(external_userid="wx_ext_001")
    )
    upsert = UpsertIdentityMappingCommand(identity_adapter=identity)(external_userid="wx_ext_001", openid="openid_001")
    assert identity.calls == ["resolve_person_identity", "upsert_identity_mapping"]
    assert resolved is not None
    assert upsert["adapter"] == "IdentityMappingAdapter"
    assert upsert["side_effect_executed"] is False


def test_customer_chat_context_still_works_with_adapter_metadata() -> None:
    result = GetCustomerChatContextQuery(repo=FixtureCustomerReadRepository())(
        CustomerChatContextRequest(external_userid="wx_ext_001", recent_message_limit=2, timeline_limit=2)
    )
    assert result["external_userid"] == "wx_ext_001"
    assert result["customer"]["external_userid"] == "wx_ext_001"
    assert result["recent_messages"]
    assert result["adapter_contract"]["recent_messages"]["archive_sync"]["adapter"] == "ArchiveSyncAdapter"
    assert not any(result["side_effect_safety"].values())


def test_customer_smoke_and_parity_remain_pass() -> None:
    smoke = importlib.import_module("tools.customer_read_model_gray_smoke")
    smoke_result = smoke.run_smoke(Namespace(old_base_url="", next_testclient=True, next_base_url="", output_md="", output_json=""))
    assert smoke_result["ok"] is True
    parity = importlib.import_module("tools.compare_customer_read_model_parity")
    parity_result = parity.run_compare(
        Namespace(
            old_fixture_dir=str(PROJECT_ROOT / "tests/fixtures/old_customer_read_model"),
            old_base_url="",
            next_testclient=True,
            next_base_url="",
            output_md="",
            output_json="",
        )
    )
    assert parity_result["ok"] is True


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d7_6_archive_contacts_identity_adapter_contract.md",
        "docs/d7_6_archive_contacts_identity_adapter_implementation_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = (PROJECT_ROOT / relpath).read_text(encoding="utf-8")
        assert "production_ready" not in text
        assert "production_approved" not in text
        assert "delete_ready" not in text


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (PROJECT_ROOT / "aicrm_next").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in text
        assert "openclaw_service" not in text
