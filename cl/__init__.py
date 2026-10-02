import os
import sqlite3
from pathlib import Path
from flask import Flask, g, current_app

def get_db():
    if "db" not in g:
        g.db=sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory=sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def close_db(exception=None):
    db=g.pop("db",None)
    if db is not None: db.close()

def init_db():
    db=get_db()
    db.executescript((Path(current_app.root_path).parent/"schema.sql").read_text())
    db.commit()

def create_app(test_config=None):
    app=Flask(__name__, instance_relative_config=True, template_folder="../templates")
    Path(app.instance_path).mkdir(parents=True,exist_ok=True)
    app.config.from_mapping(SECRET_KEY=os.environ.get("FLASK_SECRET_KEY"),GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID",""),GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET",""),DATABASE=os.environ.get("CL_DATABASE",str(Path(app.instance_path)/"cl.sqlite")))
    if test_config: app.config.update(test_config)
    app.teardown_appcontext(close_db)
    from . import auth
    auth.init_oauth(app); app.register_blueprint(auth.bp)
    from . import routes
    app.register_blueprint(routes.bp)
    @app.cli.command("init-db")
    def init_db_command(): init_db()
    return app
