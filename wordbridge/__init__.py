from datetime import timedelta

from flask import Flask


def create_app(vector_model=None, db_path=":memory:", secret_key="dev-secret-key", version="unknown"):
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.config["VECTOR_MODEL"] = vector_model
    app.config["DB_PATH"] = db_path
    app.config["VERSION"] = version
    app.secret_key = secret_key
    # A remembered player name should survive far longer than a single game
    # session (Flask's default is 31 days) — this is the cookie lifetime
    # used once a name is set via session.permanent = True.
    app.permanent_session_lifetime = timedelta(days=365)

    from .routes import bp as routes_bp

    app.register_blueprint(routes_bp)

    return app
