from flask import Flask


def create_app(vector_model=None, db_path=":memory:", secret_key="dev-secret-key"):
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.config["VECTOR_MODEL"] = vector_model
    app.config["DB_PATH"] = db_path
    app.secret_key = secret_key

    from .routes import bp as routes_bp

    app.register_blueprint(routes_bp)

    return app
