from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wecom_tag_read_inventory_documents_exact_reads_and_out_of_scope_boundaries() -> None:
    text = (ROOT / "docs/architecture/wecom_tag_read_route_inventory.md").read_text(encoding="utf-8")

    assert "/api/admin/wecom/tags" in text
    assert "/api/admin/wecom/tag-groups" in text
    assert "/api/admin/wecom/tags*" in text
    assert "/api/admin/wecom/tag-groups*" in text
    assert "/api/sidebar/signup-tags/status" in text
    assert "Questionnaire editor" in text
    assert "No separate sidebar tag catalog selector" in text
    assert "Write Out Of Scope" in text
    assert "External Side Effects Out Of Scope" in text
    assert "does not execute real WeCom sync" in text
    assert "does not create/update/delete tags or groups" in text
    assert "does not mutate customer or questionnaire tags" in text
