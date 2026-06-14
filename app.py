from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "5001"
NEXT_APP_IMPORT = "aicrm_next.main:app"


def _host() -> str:
    return os.getenv("APP_HOST", DEFAULT_HOST)


def _port() -> int:
    return int(os.getenv("APP_PORT", DEFAULT_PORT))


def run_next() -> None:
    import uvicorn

    uvicorn.run(NEXT_APP_IMPORT, host=_host(), port=_port())


def removed_legacy_command(command: str) -> None:
    raise SystemExit(
        f"{command} has been removed. AI-CRM now starts with Next runtime only. "
        "Use `python app.py run`, `python app.py health`, or `python app.py routes`. "
        "For database schema changes use Alembic migrations."
    )


def print_next_health() -> None:
    from fastapi.testclient import TestClient

    from aicrm_next.main import app

    response = TestClient(app).get("/health")
    print(
        {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "default_runtime": "ai_crm_next",
            "route_owner": response.headers.get("X-AICRM-Route-Owner", ""),
        }
    )


def print_next_routes() -> None:
    from aicrm_next.main import app

    try:
        for route in sorted(app.routes, key=lambda item: getattr(item, "path", "")):
            path = getattr(route, "path", "")
            methods = sorted(getattr(route, "methods", []) or [])
            if path:
                print(f"{','.join(methods) or '-'} {path}")
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AI-CRM runtime entry. Default runtime is AI-CRM Next; "
            "legacy Flask startup commands have been removed."
        )
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run AI-CRM Next FastAPI app (default runtime).")
    subparsers.add_parser("health", help="Check AI-CRM Next health via TestClient.")
    subparsers.add_parser("routes", help="Print AI-CRM Next route inventory.")
    cleanup = subparsers.add_parser("legacy-webhook-cleanup", help="Legacy webhook cleanup commands.")
    cleanup_subparsers = cleanup.add_subparsers(dest="legacy_cleanup_command")
    cleanup_run_due = cleanup_subparsers.add_parser("run-due", help="Run due legacy webhook cleanup candidates.")
    cleanup_run_due.add_argument("--dry-run", action="store_true", default=False, help="Preview cleanup without mutating state.")
    cleanup_run_due.add_argument("--execute", action="store_true", default=False, help="Execute due cleanup entries.")
    cleanup_run_due.add_argument("--limit", type=int, default=50)
    cleanup_run_due.add_argument("--operator", default="cli")
    targets = subparsers.add_parser("p0-1-test-targets", help="P0-1 production test target manifest commands.")
    targets_subparsers = targets.add_subparsers(dest="p0_1_targets_command")
    targets_validate = targets_subparsers.add_parser("validate", help="Validate the P0-1 production test target manifest.")
    targets_validate.add_argument("manifest", nargs="?", default="docs/queue/p0-1-production-test-targets.yaml")
    subparsers.add_parser("run-legacy", help="Removed legacy Flask startup command.")
    subparsers.add_parser("init-db-legacy", help="Removed legacy Flask database init command.")
    subparsers.add_parser("init-db", help="Removed legacy Flask database init command.")
    legacy_delete = subparsers.add_parser(
        "delete-questionnaire-submissions-legacy",
        help="Legacy fallback helper for deleting questionnaire submissions by slug.",
    )
    legacy_delete.add_argument("slug")
    legacy_delete_alias = subparsers.add_parser(
        "delete-questionnaire-submissions",
        help="Deprecated alias for delete-questionnaire-submissions-legacy.",
    )
    legacy_delete_alias.add_argument("slug")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "run":
        run_next()
        return
    if command == "health":
        print_next_health()
        return
    if command == "routes":
        print_next_routes()
        return
    if command == "legacy-webhook-cleanup":
        if getattr(args, "legacy_cleanup_command", "") == "run-due":
            from aicrm_next.platform_foundation.legacy_cleanup.jobs import print_run_due_result

            dry_run = not bool(getattr(args, "execute", False))
            if getattr(args, "dry_run", False):
                dry_run = True
            print_run_due_result(dry_run=dry_run, limit=getattr(args, "limit", 50), operator=getattr(args, "operator", "cli"))
            return
        parser.print_help()
        return
    if command == "p0-1-test-targets":
        if getattr(args, "p0_1_targets_command", "") == "validate":
            from scripts.p0_1_validate_test_targets import main as validate_targets_main

            raise SystemExit(validate_targets_main([getattr(args, "manifest", "docs/queue/p0-1-production-test-targets.yaml")]))
        parser.print_help()
        return
    if command == "run-legacy":
        removed_legacy_command(command)
        return
    if command in {"init-db", "init-db-legacy"}:
        removed_legacy_command(command)
        return
    if command in {"delete-questionnaire-submissions", "delete-questionnaire-submissions-legacy"}:
        removed_legacy_command(command)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
