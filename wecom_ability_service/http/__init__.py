from __future__ import annotations

LEGACY_COMPATIBILITY_SHIM = True


def __getattr__(name: str):
    from legacy_flask import http as _legacy_http

    return getattr(_legacy_http, name)


def register_http_routes(bp):
    from legacy_flask.http import register_http_routes as _register_http_routes

    return _register_http_routes(bp)


def create_http_blueprint():
    from legacy_flask.http import create_http_blueprint as _create_http_blueprint

    return _create_http_blueprint()


__all__ = [
    "LEGACY_COMPATIBILITY_SHIM",
    "bp",
    "create_http_blueprint",
    "register_http_routes",
]
