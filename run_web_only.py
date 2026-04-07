from __future__ import annotations

from waitress import serve

import db
from config import load_config
from web import create_app


def main() -> None:
    config = load_config()
    db.set_database_path(config.database_path)
    db.init_db()
    app = create_app(config)
    serve(app, host="0.0.0.0", port=config.web_port)


if __name__ == "__main__":
    main()
