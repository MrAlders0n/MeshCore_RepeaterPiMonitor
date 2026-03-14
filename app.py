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

    # Authentication
    @app.before_request
    def require_auth():
        if config.PASSWORD is None:
            return None
        # Allow login page and static files without auth
        if request.endpoint in ("login", "static", "auth_nonce"):
            return None
        if session.get("authenticated"):
            return None
        # API / WebSocket paths get 401; browser pages get redirected
        if request.path.startswith("/api/") or request.path.startswith("/ws/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login"))

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
        return redirect(url_for("login"))

    # Root route serves dashboard
    @app.route("/")
    def index():
        return render_template(
            "index.html",
            auth_enabled=bool(
                os.environ.get("MESHCORE_PASSWORD_HASH") or os.environ.get("MESHCORE_PASSWORD")
            ),
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
