from __future__ import annotations

from .connection import (  # noqa: F401
    PostgresConnection,
    close_db,
    dict_factory,
    get_db,
    get_db_backend,
)
from .helpers import (  # noqa: F401
    _postgres_table_columns,
    _sqlite_normalized_conversion_pool_sql,
    _sqlite_table_columns,
    _sqlite_table_exists,
    _sqlite_table_sql,
)
from .migrations import (  # noqa: F401
    _ensure_automation_agent_prompt_defaults,
    _ensure_automation_sop_v1_seed_data,
)


def init_db() -> None:
    from .connection import get_db, get_db_backend
    from .migrations.postgres_migrations import _init_postgres
    from .migrations.sqlite_migrations import _init_sqlite

    db = get_db()
    if get_db_backend() == "postgres":
        _init_postgres(db)
    else:
        _init_sqlite(db)


def migrate_db() -> None:
    init_db()


def init_app(app) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized the database.")
