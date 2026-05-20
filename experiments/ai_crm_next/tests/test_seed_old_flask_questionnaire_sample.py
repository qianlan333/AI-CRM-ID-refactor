from __future__ import annotations

import pytest

from tools import seed_old_flask_questionnaire_sample as seed_tool


SAFE_URL = "postgresql://aicrm_old_flask_test:secret@127.0.0.1:5432/aicrm_old_flask_test"


def test_questionnaire_seed_guard_accepts_only_local_old_flask_test_db() -> None:
    result = seed_tool.validate_database_url(SAFE_URL)
    assert result.host == "127.0.0.1"
    assert result.database_name == "aicrm_old_flask_test"
    assert result.redacted_url == "postgresql://aicrm_old_flask_test:***@127.0.0.1:5432/aicrm_old_flask_test"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@example.com:5432/aicrm_old_flask_test",
        "postgresql://user:pass@127.0.0.1:5432/aicrm_prod",
        "mysql://user:pass@127.0.0.1:3306/aicrm_old_flask_test",
    ],
)
def test_questionnaire_seed_guard_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        seed_tool.validate_database_url(url)


def test_questionnaire_seed_default_is_dry_run_without_writes() -> None:
    result = seed_tool.seed_sample(SAFE_URL, apply=False)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["sample"]["slug"] == "questionnaire_slug_masked_001"
    assert result["sample"]["openid"] == "openid_masked_001"
    assert "questionnaire_external_push_logs" not in result["tables"]


def test_questionnaire_seed_tool_does_not_import_old_backend() -> None:
    source = seed_tool.Path(seed_tool.__file__).read_text(encoding="utf-8")
    assert "import wecom_ability_service" not in source
    assert "from wecom_ability_service" not in source
    assert "import openclaw_service" not in source
    assert "from openclaw_service" not in source
