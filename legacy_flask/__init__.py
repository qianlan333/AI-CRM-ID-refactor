from __future__ import annotations

LEGACY_FLASK_ARCHIVE_PACKAGE = True


def create_app(test_config: dict | None = None):
    from legacy_flask.app_factory import create_app as _create_app

    return _create_app(test_config)


__all__ = ["LEGACY_FLASK_ARCHIVE_PACKAGE", "create_app"]
