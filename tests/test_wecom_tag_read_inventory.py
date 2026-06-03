from __future__ import annotations

from pathlib import Path


INVENTORY = Path("docs/architecture/wecom_tag_read_route_inventory.md")


def test_wecom_tag_read_inventory_covers_read_write_selector_and_sync_scope() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for route in [
        "/api/admin/wecom/tags",
        "/api/admin/wecom/tags/{tag_id}",
        "/api/admin/wecom/tag-groups",
        "/api/admin/wecom/tag-groups/{group_id}",
        "/api/admin/wecom/tags*",
        "/api/admin/wecom/tag-groups*",
        "/api/sidebar/signup-tags/status",
    ]:
        assert route in text

    assert "questionnaire editor tag picker" in text
    assert "channel admission tag picker" in text
    assert "automation agent tag picker" in text
    assert "No separate sidebar tag catalog selector" in text
    assert "Write Out Of Scope" in text
    assert "External Side Effects Out Of Scope" in text
    assert "does not execute real WeCom sync" in text
    assert "does not create/update/delete tags or groups" in text
    assert "does not mutate customer or questionnaire tags" in text
    assert "production_unavailable" in text
    assert "local_contract_probe" in text


def test_wecom_tag_read_inventory_marks_external_systems_out_of_scope() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Payment, storage, OpenClaw, and automation runtime remain out of scope" in text
    assert "does not call WeCom" in text
    assert "Empty production projection tables return an empty catalog rather than fixture data" in text
