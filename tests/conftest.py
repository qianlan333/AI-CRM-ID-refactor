"""顶层 pytest fixtures — PG-only。

2026-05 砍掉 SQLite 后，所有测试**必须**连 PG。本地跑：

    docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16
    DATABASE_URL=postgresql://test:test@localhost:5432/test pytest

CI 上 service container 自动起 PG 并设 DATABASE_URL。

提供的 fixture：
- ``app``：每个 test 一个干净 Flask app + truncate 关键表
- ``client``：``app.test_client()``

老测试以前自己用 ``tmp_path / "test.sqlite3"`` + ``DATABASE_PATH`` 起 SQLite，
迁移到这个顶层 fixture 后只需 ``def test_xxx(app, client):`` 即可。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

# 让 import 能找到项目包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# 测试间需要清理的关键表（FK 反向顺序：子表先清，自动级联）
_TABLES_TO_TRUNCATE = [
    "automation_touch_delivery_log",
    "automation_frequency_consumption",
    "automation_frequency_budget",
    "campaign_members",
    "campaign_steps",
    "campaign_segments",
    "campaigns",
    "cloud_approval_tokens",
    "cloud_broadcast_plans",
    "cloud_agent_audit_log",
    "automation_member",
    "segments",
    "image_library",
    "miniprogram_library",
    "questionnaire_submission_answers",
    "questionnaire_submissions",
    "questionnaire_options",
    "questionnaire_questions",
    "questionnaires",
    "admin_users",
    "contacts",
    "people",
    "external_contact_bindings",
    "archived_messages",
]


def _ensure_pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "PG required. Run: "
            "docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test "
            "-e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16; "
            "then DATABASE_URL=postgresql://test:test@localhost:5432/test pytest"
        )
    return url


def _run_schema_with_retries(db: Any, script: str, *, max_passes: int = 3) -> None:
    """跑 schema_postgres.sql，对前向 FK 引用容错（少数 CREATE 语句要等被引用表后建好）。"""
    statements = [s.strip() for s in script.split(";") if s.strip()]
    pending = statements
    for _ in range(max_passes):
        if not pending:
            return
        cursor = db._conn.cursor()
        next_pending: list[str] = []
        for stmt in pending:
            try:
                cursor.execute(stmt)
                db._conn.commit()
            except Exception:
                db._conn.rollback()
                next_pending.append(stmt)
        cursor.close()
        if len(next_pending) == len(pending):
            return  # 没进展 — 残留就是真坏掉的
        pending = next_pending


def build_pg_test_app(tmp_path, **extra_config: Any):
    """老测试兼容 helper：起 PG 模式 app，允许传 extra_config 覆盖默认。

    用法（替换老 SQLite fixture）：

        @pytest.fixture
        def app(tmp_path):
            from tests.conftest import build_pg_test_app
            with build_pg_test_app(tmp_path, MCP_BEARER_TOKEN="mcp-token") as app:
                yield app
    """
    return _build_app_context(tmp_path, extra_config)


class _AppContextManager:
    """支持 with-statement，自动 truncate 隔离。"""

    def __init__(self, tmp_path, extra_config):
        self.tmp_path = tmp_path
        self.extra_config = extra_config
        self._app = None
        self._ctx = None

    def __enter__(self):
        database_url = _ensure_pg_url()
        private_key = self.tmp_path / "wecom_private_key.pem"
        sdk_lib = self.tmp_path / "libWeWorkFinanceSdk_C.so"
        private_key.write_text("fake-key", encoding="utf-8")
        sdk_lib.write_text("fake-so", encoding="utf-8")

        from wecom_ability_service import create_app
        from wecom_ability_service.db import get_db, init_db

        config = {
            "TESTING": True,
            "DATABASE_URL": database_url,
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key),
            "WECOM_SDK_LIB_PATH": str(sdk_lib),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
        config.update(self.extra_config)

        self._app = create_app(test_config=config)
        self._ctx = self._app.app_context()
        self._ctx.push()

        db = get_db()
        schema_path = Path(self._app.root_path) / "schema_postgres.sql"
        if schema_path.exists():
            _run_schema_with_retries(db, schema_path.read_text(encoding="utf-8"))
            db.commit()
        init_db()
        cur = db.cursor()
        for table in _TABLES_TO_TRUNCATE:
            try:
                cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
            except Exception:
                db.rollback()
        db.commit()
        return self._app

    def __exit__(self, *args):
        if self._ctx is not None:
            self._ctx.pop()


def _build_app_context(tmp_path, extra_config):
    return _AppContextManager(tmp_path, extra_config)


@pytest.fixture
def app(tmp_path) -> Iterator[Any]:
    """干净 Flask app + 真 PG，每个 test 隔离。"""
    database_url = _ensure_pg_url()

    # WeCom SDK / private key 等运行时依赖文件（test 用 fake 占位）
    private_key = tmp_path / "wecom_private_key.pem"
    sdk_lib = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key.write_text("fake-key", encoding="utf-8")
    sdk_lib.write_text("fake-so", encoding="utf-8")

    from wecom_ability_service import create_app
    from wecom_ability_service.db import get_db, init_db

    app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE_URL": database_url,
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key),
            "WECOM_SDK_LIB_PATH": str(sdk_lib),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        # 跑 schema_postgres.sql 建表（容错前向 FK 引用），再 init_db 跑 ALTER 补丁
        db = get_db()
        schema_path = Path(app.root_path) / "schema_postgres.sql"
        if schema_path.exists():
            _run_schema_with_retries(db, schema_path.read_text(encoding="utf-8"))
            db.commit()
        init_db()
        # truncate 隔离
        cur = db.cursor()
        for table in _TABLES_TO_TRUNCATE:
            try:
                cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
            except Exception:
                db.rollback()
        db.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()
