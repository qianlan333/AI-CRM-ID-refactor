from __future__ import annotations

from flask import Blueprint

from .admin_jobs import register_routes as register_admin_jobs_console_routes
from .admin_customers import register_routes as register_admin_customer_console_routes
from .admin_audit import register_routes as register_admin_audit_console_routes
from .admin_mcp import register_routes as register_admin_mcp_console_routes
from .admin_operations import register_routes as register_admin_operations_console_routes
from .admin_questionnaire_console import register_routes as register_admin_questionnaire_console_routes
from .admin_config import register_routes as register_admin_config_routes
from .admin_console import register_routes as register_admin_console_routes
from .admin_dashboard import register_routes as register_admin_dashboard_routes
from .admin_class_user import register_routes as register_admin_class_user_routes
from .admin_questionnaires import register_routes as register_admin_questionnaires_routes
from .admin_user_ops import register_routes as register_admin_user_ops_routes
from .archive import register_routes as register_archive_routes
from .callbacks import register_routes as register_callback_routes
from .contacts import register_routes as register_contacts_routes
from .customer_center import register_routes as register_customer_center_routes
from .customer_timeline import register_routes as register_customer_timeline_routes
from .group_chats import register_routes as register_group_chat_routes
from .identity import register_routes as register_identity_routes
from .ops import register_routes as register_ops_routes
from .public_questionnaires import register_routes as register_public_questionnaire_routes
from .settings_ops import register_routes as register_settings_routes
from .sidebar import register_routes as register_sidebar_routes
from .tags import register_routes as register_tag_routes
from .tasks import register_routes as register_task_routes

HTTP_CONTROLLER_RULES = (
    "controller only parses request input, validates/coerces primitives, delegates to services/runtime helpers, and builds responses",
    "controller must not execute raw SQL directly",
    "controller must not call third-party HTTP APIs directly",
    "controller must not implement complex business rules or job orchestration inline",
)

HTTP_ROUTE_MODULES = {
    "sidebar": "wecom_ability_service.http.sidebar",
    "identity": "wecom_ability_service.http.identity",
    "ops": "wecom_ability_service.http.ops",
    "settings": "wecom_ability_service.http.settings_ops",
    "customer_center": "wecom_ability_service.http.customer_center",
    "customer_timeline": "wecom_ability_service.http.customer_timeline",
    "archive": "wecom_ability_service.http.archive",
    "contacts": "wecom_ability_service.http.contacts",
    "group_chats": "wecom_ability_service.http.group_chats",
    "callbacks": "wecom_ability_service.http.callbacks",
    "tasks": "wecom_ability_service.http.tasks",
    "tags": "wecom_ability_service.http.tags",
    "admin_console": "wecom_ability_service.http.admin_console",
    "admin_jobs": "wecom_ability_service.http.admin_jobs",
    "admin_audit": "wecom_ability_service.http.admin_audit",
    "admin_customers": "wecom_ability_service.http.admin_customers",
    "admin_mcp": "wecom_ability_service.http.admin_mcp",
    "admin_operations": "wecom_ability_service.http.admin_operations",
    "admin_questionnaire_console": "wecom_ability_service.http.admin_questionnaire_console",
    "admin_config": "wecom_ability_service.http.admin_config",
    "admin_dashboard": "wecom_ability_service.http.admin_dashboard",
    "admin_user_ops": "wecom_ability_service.http.admin_user_ops",
    "admin_class_user": "wecom_ability_service.http.admin_class_user",
    "admin_questionnaires": "wecom_ability_service.http.admin_questionnaires",
    "public_questionnaires": "wecom_ability_service.http.public_questionnaires",
}

HTTP_ROUTE_PLACEMENT = {
    "customer": (
        "customer_center.py for /api/customers* list/detail",
        "customer_timeline.py for /api/customers/<external_userid>/timeline",
        "contacts.py and identity.py for contact binding / identity resolution",
    ),
    "admin": (
        "admin_console.py for /admin home, shell helpers, and legacy shell embeds",
        "admin_jobs.py for /admin/jobs and confirmed sync/task actions",
        "admin_audit.py for /admin/audit governance page and /api/admin/audit/logs",
        "admin_customers.py for /admin/customers* pages and customer detail actions",
        "admin_mcp.py for /admin/mcp console, preflight, and safe sample-call actions",
        "admin_operations.py for /admin/user-ops, /admin/class-users, and confirmed operations actions",
        "admin_questionnaire_console.py for /admin/questionnaires* shell pages",
        "admin_config.py for /admin/config* pages and /api/admin/config* controllers",
        "admin_dashboard.py for /api/admin/dashboard/* shell status",
        "admin_user_ops.py for /api/admin/user-ops* and /admin/user-ops/ui",
        "admin_class_user.py for /api/admin/class-user-management* and /admin/class-user-backoffice/ui",
        "admin_questionnaires.py for /api/admin/questionnaires* and /admin/questionnaires/ui",
    ),
    "callbacks": (
        "callbacks.py for callback controllers only",
        "callback_runtime.py for callback auth/decrypt/dispatch runtime",
        "background_jobs.py for async task dispatch and callback background handlers",
    ),
    "ops_settings": (
        "ops.py for /health, /archive/messages, /api/init-db, /api/ops/status",
        "settings_ops.py for /api/settings",
    ),
}

HTTP_ROUTE_REGISTRARS = (
    ("sidebar", register_sidebar_routes),
    ("identity", register_identity_routes),
    ("ops", register_ops_routes),
    ("settings", register_settings_routes),
    ("admin_console", register_admin_console_routes),
    ("admin_jobs", register_admin_jobs_console_routes),
    ("admin_audit", register_admin_audit_console_routes),
    ("admin_customers", register_admin_customer_console_routes),
    ("admin_mcp", register_admin_mcp_console_routes),
    ("admin_operations", register_admin_operations_console_routes),
    ("admin_questionnaire_console", register_admin_questionnaire_console_routes),
    ("admin_config", register_admin_config_routes),
    ("admin_dashboard", register_admin_dashboard_routes),
    ("admin_user_ops", register_admin_user_ops_routes),
    ("admin_class_user", register_admin_class_user_routes),
    ("admin_questionnaires", register_admin_questionnaires_routes),
    ("customer_center", register_customer_center_routes),
    ("customer_timeline", register_customer_timeline_routes),
    ("public_questionnaires", register_public_questionnaire_routes),
    ("archive", register_archive_routes),
    ("contacts", register_contacts_routes),
    ("group_chats", register_group_chat_routes),
    ("callbacks", register_callback_routes),
    ("tasks", register_task_routes),
    ("tags", register_tag_routes),
)


def register_http_routes(bp: Blueprint) -> Blueprint:
    for _, register_routes in HTTP_ROUTE_REGISTRARS:
        register_routes(bp)
    return bp


def create_http_blueprint() -> Blueprint:
    bp = Blueprint("api", __name__)
    return register_http_routes(bp)


bp = create_http_blueprint()

__all__ = [
    "HTTP_CONTROLLER_RULES",
    "HTTP_ROUTE_MODULES",
    "HTTP_ROUTE_PLACEMENT",
    "HTTP_ROUTE_REGISTRARS",
    "bp",
    "create_http_blueprint",
    "register_http_routes",
]
