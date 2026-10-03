import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from flask import Flask, g, current_app
from authlib.integrations.flask_client import OAuth


def get_db():
    if "db" not in g:
        database_url = current_app.config["DATABASE_URL"]
        if database_url:
            g.db = psycopg.connect(database_url, row_factory=dict_row)
        else:
            g.db = sqlite3.connect(current_app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _is_postgres():
    return bool(current_app.config.get("DATABASE_URL"))


def init_db():
    db = get_db()
    schema_name = "schema_postgres.sql" if _is_postgres() else "schema.sql"
    schema = (Path(current_app.root_path).parent / schema_name).read_text()
    if _is_postgres():
        db.execute(schema)
    else:
        db.executescript(schema)
    db.commit()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True, template_folder="../templates")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    database = os.environ.get("CL_DATABASE", str(Path(app.instance_path) / "cl.sqlite"))
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "cl-local"),
        DATABASE=database,
        DATABASE_URL=os.environ.get("DATABASE_URL", "").strip(),
        GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID", ""),
        GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        BLOG_ALLOWED_EMAILS=os.environ.get("BLOG_ALLOWED_EMAILS", "").strip(),
    )
    if test_config:
        app.config.update(test_config)

    oauth = OAuth()
    oauth.init_app(app)
    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    app.extensions["oauth"] = oauth

    app.teardown_appcontext(close_db)
    from . import routes
    app.register_blueprint(routes.bp)

    @app.cli.command("init-db")
    def init_db_command():
        init_db()

    return app
