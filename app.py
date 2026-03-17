import bcrypt as _bc, secrets as _secrets
import logging
import os
import signal
import sys
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_sock import Sock
import config
from database.schema import init_db
from database import models
from api.routes import api
from api.terminal import register_terminal_routes
from collector.stats_poller import StatsPoller
from collector.sensor_poller import SensorPoller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Methods that require authentication even on public installs
_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _auth_enabled():
    return bool(
        os.environ.get("MESHCORE_PASSWORD_HASH") or os.environ.get("MESHCORE_PASSWORD")
    )


def _is_authenticated():
    return session.get("authenticated", False)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY or os.urandom(24)

    # Initialize database
    init_db(config.DB_PATH)
    models.init(config.DB_PATH)

    # Register API blueprint
    app.register_blueprint(api)

    # Initialize WebSocket support
    sock = Sock(app)
    register_terminal_routes(sock)

    @app.before_request
    def require_auth():
        # Always allow static files and login/logout
        if request.endpoint in ("login", "logout", "static", "auth_nonce"):
            return None

        # If auth is not configured, everything is public
        if not _auth_enabled():
            return None

        # GET requests to the dashboard and read-only API are always public
        if request.method == "GET":
            return None

        # WebSocket connections require authentication
        if request.path.startswith("/ws/"):
            if not _is_authenticated():
                return jsonify({"error": "Authentication required"}), 401
            return None

        # POST/PUT/DELETE/PATCH on API require authentication
        if request.path.startswith("/api/") and request.method in _WRITE_METHODS:
            if not _is_authenticated():
                return jsonify({"error": "Authentication required"}), 401
            return None

        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            submitted = request.form.get("password", "")
            pw_hash   = os.environ.get("MESHCORE_PASSWORD_HASH", "")
            pw_plain  = os.environ.get("MESHCORE_PASSWORD", "")
            if pw_hash:
                ok = _bc.checkpw(submitted.encode(), pw_hash.encode())
            elif pw_plain:
                ok = _secrets.compare_digest(submitted, pw_plain)
            else:
                ok = False
            if ok:
                session["authenticated"] = True
                return redirect(url_for("index"))
            error = "Invalid password"
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    # Root route serves dashboard — always accessible
    @app.route("/")
    def index():
        return render_template(
            "index.html",
            auth_enabled=_auth_enabled(),
            is_authenticated=_is_authenticated(),
        )

    # Start collector
    poller = StatsPoller()
    app.config["poller"] = poller
    poller.start()

    # Start sensor poller
    sensor_poller = None
    if config.SENSOR_POLL_ENABLED:
        sensor_poller = SensorPoller()
        app.config["sensor_poller"] = sensor_poller
        sensor_poller.start()

    def shutdown_handler(signum, frame):
        logger.info("Shutting down collector...")
        poller.stop()
        if sensor_poller:
            sensor_poller.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        use_reloader=False,
    )
