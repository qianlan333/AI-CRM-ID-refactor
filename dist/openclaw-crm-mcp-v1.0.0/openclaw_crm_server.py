from __future__ import annotations

import sys

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db


def main() -> None:
    app = create_app()

    if len(sys.argv) > 1 and sys.argv[1] == "init-db":
        with app.app_context():
            init_db()
        print("Database initialized.")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        host = app.config["APP_HOST"]
        port = int(app.config["APP_PORT"])
        app.run(host=host, port=port, debug=app.config["DEBUG"])
        return

    print("Usage: python openclaw_crm_server.py [init-db|run]")


if __name__ == "__main__":
    main()
