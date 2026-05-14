from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_deploy_loads_postgres_env_before_init_db():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    env_source_index = workflow.index("source /home/ubuntu/.openclaw-wecom-pg.env")
    database_url_guard_index = workflow.index('test -n "${DATABASE_URL:-}"')
    init_db_index = workflow.index("python3 app.py init-db")

    assert env_source_index < database_url_guard_index < init_db_index


def test_production_deploy_stashes_dirty_worktree_before_pull():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    stash_index = workflow.index("git stash push --include-untracked")
    pull_index = workflow.index("git pull --ff-only origin main")

    assert stash_index < pull_index


def test_pg_only_ops_tools_do_not_expose_sqlite_entrypoints():
    assert not (ROOT / "scripts" / "backup_sqlite.sh").exists()

    seed_demo = (ROOT / "scripts" / "seed_automation_conversion_demo.py").read_text(encoding="utf-8")
    campaign_scheduler = (ROOT / "scripts" / "run_campaign_scheduler.py").read_text(encoding="utf-8")
    broadcast_worker = (ROOT / "scripts" / "run_broadcast_queue_worker.py").read_text(encoding="utf-8")
    ops_runtime = (ROOT / "wecom_ability_service" / "http" / "ops_runtime.py").read_text(encoding="utf-8")

    assert "--database-path" not in seed_demo
    assert "DATABASE_PATH`` / ``DATABASE_URL" not in campaign_scheduler
    assert "DATABASE_PATH`` / ``DATABASE_URL" not in broadcast_worker
    assert "sqlite_path" not in ops_runtime
