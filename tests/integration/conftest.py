"""Integration test fixtures — 跑核心业务路径在真实数据库（PG / SQLite）上。

行为：
- 默认（无环境变量）：用临时 SQLite 文件，每次 session 一个新文件，自动 init_db
- 设置 ``DATABASE_URL=postgresql://...``：用 PG，每次 test 跑前 ``TRUNCATE`` 关键表
  确保 test 间隔离

CI 上跑 PG 集成测试只需 ``DATABASE_URL=postgresql://test:test@localhost:5432/test pytest tests/integration/``。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

import pytest

# 让 import 能找到项目包
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# 测试时希望被 truncate 的表（仅 PG 模式生效；SQLite 整库重建）
# 顺序按 FK 依赖反向：子表先清
_PG_TABLES_TO_TRUNCATE = [
    "automation_touch_delivery_log",
    "automation_frequency_consumption",
    "campaign_members",
    "campaign_steps",
    "campaign_segments",
    "campaigns",
    "cloud_approval_tokens",
    "cloud_broadcast_plans",
    "cloud_agent_audit_log",
    "automation_frequency_budget",
    "segments",
    "image_library",
    "miniprogram_library",
]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Flask app + 真实数据库。yield 后自动清理。"""
    database_url = os.environ.get("DATABASE_URL", "").strip()

    if database_url:
        # PG 模式：env 已经指向 PG
        from wecom_ability_service import create_app
        from wecom_ability_service.db import get_db

        app = create_app(test_config={"TESTING": True, "DATABASE_URL": database_url})
        with app.app_context():
            # 全新空数据库下，``init_db -> _init_postgres`` 开头有 ALTER / CREATE INDEX
            # 引用 ``automation_channel`` 等基础表，但 schema_postgres.sql 在该函数 **末尾**
            # 才执行。生产环境老库基础表早就存在，所以没问题；CI 全新 PG 必须先手动跑 schema
            # 文件建表才行。
            from pathlib import Path
            db = get_db()
            schema_path = Path(app.root_path) / "schema_postgres.sql"
            if schema_path.exists():
                db.executescript(schema_path.read_text(encoding="utf-8"))
                db.commit()
            from wecom_ability_service.db import init_db as _init
            _init()
            cur = db.cursor()
            for table in _PG_TABLES_TO_TRUNCATE:
                try:
                    cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
                except Exception:
                    db.rollback()  # 表不存在就跳过
            db.commit()
            yield app
    else:
        # SQLite 模式：临时文件，session 后删
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        try:
            monkeypatch.setenv("DATABASE_PATH", db_path)
            monkeypatch.setenv("DATABASE_URL", "")
            from wecom_ability_service import create_app

            app = create_app(test_config={"TESTING": True, "DATABASE_PATH": db_path, "DATABASE_URL": ""})
            with app.app_context():
                from wecom_ability_service.db import init_db as _init
                _init()
                yield app
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


@pytest.fixture
def db_backend() -> str:
    """读 ``DATABASE_URL`` 判断当前测试模式 — 给条件 skip 用。"""
    return "postgres" if os.environ.get("DATABASE_URL", "").strip() else "sqlite"
