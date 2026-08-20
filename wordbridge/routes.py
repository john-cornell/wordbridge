from flask import Blueprint, current_app, jsonify, request, session

from .db import (
    clear_attempts,
    get_last_threshold,
    init_db,
    list_attempts,
    list_high_scores,
    save_attempt,
    set_last_threshold,
)
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


@bp.get("/scores")
def scores_page():
    return current_app.send_static_file("scores.html")


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

    chain = Chain(
        model,
        start_word=start_word,
        target_word=target_word,
        threshold=get_last_threshold(_get_db_conn()),
    )
    session["chain"] = chain.to_dict()

    return jsonify(
        start_word=start_word,
        target_word=target_word,
        start_target_similarity=chain.start_target_similarity(),
        threshold=chain.threshold,
    )


@bp.post("/api/game/threshold")
def set_threshold():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed or chain.steps:
        return jsonify(error="Threshold is locked once the game has started."), 400

    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        threshold = float(payload.get("threshold"))
    except (TypeError, ValueError):
        return jsonify(error="threshold must be a number"), 400
    if not 0 <= threshold <= 1:
        return jsonify(error="threshold must be between 0 and 1"), 400

    chain.threshold = threshold
    session["chain"] = chain.to_dict()
    set_last_threshold(_get_db_conn(), threshold)

    return jsonify(threshold=chain.threshold)


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
    winning_connection = chain.winning_connection()
    won = winning_connection is not None
    if won:
        save_attempt(_get_db_conn(), chain)
        chain.mark_won()

    session["chain"] = chain.to_dict()

    return jsonify(
        word=step.word,
        neighbor_similarity=step.neighbor_similarity,
        target_similarity=step.target_similarity,
        is_digression=step.is_digression,
        similarities=step.similarities,
        winning_connection=winning_connection,
        score=chain.score(),
        won=won,
        over_soft_cap=chain.is_over_soft_cap(),
    )


@bp.post("/api/game/hint")
def hint():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed:
        return jsonify(error="This game is already complete — start a new game."), 400

    current_word = chain.steps[-1].word if chain.steps else chain.start_word
    continuation = model.find_route(current_word, chain.target_word, win_threshold=chain.threshold)

    if not continuation:
        return jsonify(hint_word=None, cost=0, score=chain.score())

    cost = chain.use_hint()
    session["chain"] = chain.to_dict()

    return jsonify(hint_word=continuation[0], cost=cost, score=chain.score())


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
    played_words = [chain.start_word] + [step.word for step in chain.steps]

    suggested_continuation = model.find_route(
        current_word, chain.target_word, max_hops=8, neighbors_per_hop=40, win_threshold=chain.threshold
    )
    if suggested_continuation is not None:
        route = played_words + suggested_continuation
    else:
        # Wherever the player wandered to didn't lead anywhere — try a fresh
        # route from the true start instead of just echoing their dead end.
        fresh_route = model.find_route(
            chain.start_word,
            chain.target_word,
            max_hops=8,
            neighbors_per_hop=40,
            win_threshold=chain.threshold,
        )
        route = [chain.start_word] + fresh_route if fresh_route is not None else played_words

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

    if chain.won:
        return jsonify(error="Can't restart a won game — start a new game instead."), 400

    chain.restart()
    session["chain"] = chain.to_dict()

    return jsonify(
        start_word=chain.start_word,
        target_word=chain.target_word,
        start_target_similarity=chain.start_target_similarity(),
        threshold=chain.threshold,
    )


@bp.get("/api/history")
def history():
    return jsonify(attempts=list_attempts(_get_db_conn()))


@bp.get("/api/high_scores")
def high_scores():
    return jsonify(scores=list_high_scores(_get_db_conn()))


@bp.post("/api/high_scores/clear")
def clear_high_scores():
    clear_attempts(_get_db_conn())
    return jsonify(cleared=True)
