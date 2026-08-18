from flask import Flask, jsonify


def create_app(vector_model=None, db_path=":memory:"):
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.config["VECTOR_MODEL"] = vector_model
    app.config["DB_PATH"] = db_path

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    return app
