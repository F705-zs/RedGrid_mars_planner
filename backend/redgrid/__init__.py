"""RedGrid Backend (Flask). Create the app with create_app(); run with `flask --app redgrid run`."""
from __future__ import annotations

from flask import Flask, g, jsonify
from flask_cors import CORS

from . import db, errors
from .config import Config


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    db.check_sqlite_version()
    from . import registry
    app.extensions["redgrid"] = registry.verify(app.config)   # every puzzle piece checked at start-up
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    errors.register(app)

    from .controllers import catalog, location, mission, report, route
    for bp in (catalog.bp, location.bp, mission.bp, route.bp, report.bp):
        app.register_blueprint(bp, url_prefix="/api")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "version": "6.0.0"})

    @app.after_request
    def commit(resp):
        if "db" in g and resp.status_code < 400:
            g.db.commit()
        return resp

    app.teardown_appcontext(db.close_db)

    from . import cli
    cli.register(app)
    return app
