from __future__ import annotations

from .connection import (  # noqa: F401
    PostgresConnection,
    close_db,
    dict_factory,
    get_db,
    get_db_backend,
)
from .dialect import (  # noqa: F401
    cast_text,
    coalesce_text,
    is_postgres,
    is_sqlite,
    nonempty,
    upsert_clause,
)


def init_db() -> None:
    from .migrations.postgres_migrations import _init_postgres
    from .migrations.sqlite_migrations import _init_sqlite

    db = get_db()
    if get_db_backend() == "postgres":
        _init_postgres(db)
    else:
        _init_sqlite(db)

    # 启动期幂等 seed —— 系统默认分层 + 频次预算（已存在不覆盖）
    try:
        from ..domains.segments.service import seed_default_segments

        seed_default_segments()
    except Exception as exc:  # pragma: no cover - defensive: 不阻塞主流程
        import logging

        logging.getLogger(__name__).warning("seed_default_segments skipped: %s", exc)
    try:
        from ..domains.marketing_automation.frequency_budget_service import (
            ensure_default_budgets,
        )

        ensure_default_budgets()
    except Exception as exc:  # pragma: no cover - defensive
        import logging

        logging.getLogger(__name__).warning("ensure_default_budgets skipped: %s", exc)


def migrate_db() -> None:
    init_db()


def init_app(app) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized the database.")
