from flask import Blueprint, current_app, jsonify, request, session

from .db import init_db, list_attempts, save_attempt
from .game import Chain

bp = Blueprint("routes", __name__)


def _get_model():
    return current_app.config["VECTOR_MODEL"]


def _get_db_conn():
    if "_db_conn" not in current_app.config:
        current_app.config["_db_conn"] = init_db(current_app.config["DB_PATH"])
    return current_app.config["_db_conn"]


@bp.get("/")
def index():
    return current_app.send_static_file("index.html")


@bp.get("/api/health")
def health():
    return jsonify(status="ok")


@bp.post("/api/game/new")
def new_game():
    model = _get_model()
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    mode = payload.get("mode", "random")

    if mode == "manual":
        word1 = payload.get("word1", "").strip().lower()
        word2 = payload.get("word2", "").strip().lower()
        if not model.contains(word1):
            return jsonify(error=f"'{word1}' is not a recognized word"), 400
        if not model.contains(word2):
            return jsonify(error=f"'{word2}' is not a recognized word"), 400
        start_word, target_word = word1, word2
    else:
        start_word, target_word = model.random_pair()

    chain = Chain(model, start_word=start_word, target_word=target_word)
    session["chain"] = chain.to_dict()

    return jsonify(
        start_word=start_word,
        target_word=target_word,
        start_target_similarity=chain.start_target_similarity(),
    )


@bp.post("/api/game/word")
def add_word():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed:
        return jsonify(error="This game is already complete — start a new game."), 400

    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    word = payload.get("word", "").strip().lower()

    try:
        step = chain.add_word(word)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    # chain.completed is guaranteed False here (an already-completed chain
    # returns 400 above, before add_word is ever called), so this is the
    # first time this chain has met the win condition.
    won = chain.is_won()
    if won:
        save_attempt(_get_db_conn(), chain)
        chain.mark_completed()

    session["chain"] = chain.to_dict()

    return jsonify(
        word=step.word,
        neighbor_similarity=step.neighbor_similarity,
        target_similarity=step.target_similarity,
        is_digression=step.is_digression,
        similarities=step.similarities,
        score=chain.score(),
        won=won,
        over_soft_cap=chain.is_over_soft_cap(),
    )


@bp.post("/api/game/give_up")
def give_up():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed:
        return jsonify(error="This game is already complete — start a new game."), 400

    best_step = chain.best_step()
    current_word = chain.steps[-1].word if chain.steps else chain.start_word
    route = model.find_route(current_word, chain.target_word)
    chain.mark_completed()
    session["chain"] = chain.to_dict()

    return jsonify(
        given_up=True,
        best_word=best_step.word if best_step else None,
        best_similarity=best_step.target_similarity if best_step else None,
        route=route,
    )


@bp.post("/api/game/restart")
def restart_game():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])
    chain.restart()
    session["chain"] = chain.to_dict()

    return jsonify(
        start_word=chain.start_word,
        target_word=chain.target_word,
        start_target_similarity=chain.start_target_similarity(),
    )


@bp.get("/api/history")
def history():
    return jsonify(attempts=list_attempts(_get_db_conn()))
