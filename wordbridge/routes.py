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

_SEARCH_PARAMS = dict(max_hops=8, neighbors_per_hop=40)
_PAR_SEARCH_PARAMS = dict(max_hops=10, neighbors_per_hop=60)
_PAR_FALLBACK_SEARCH_PARAMS = dict(max_hops=15, neighbors_per_hop=100)
_PAR_REROLL_ATTEMPTS = 20
_MAX_PLAYER_NAME_LENGTH = 30


def _get_model():
    return current_app.config["VECTOR_MODEL"]


def _get_db_conn():
    if "_db_conn" not in current_app.config:
        current_app.config["_db_conn"] = init_db(current_app.config["DB_PATH"])
    return current_app.config["_db_conn"]


def _already_used_words(chain):
    return {chain.start_word} | {step.word for step in chain.steps}


def _find_hint_word(chain, model):
    """Pick a single next word that makes real progress: bridge the closest
    not-yet-connected pair of known points (from either the start's side or
    the target's side), falling back to searching straight toward the target."""
    exclude = _already_used_words(chain)
    anchor, other = chain.closest_unconnected_pair()

    bridge = model.find_route(anchor, other, exclude=exclude, win_threshold=chain.threshold, **_SEARCH_PARAMS)
    if bridge is not None:
        return bridge[0]

    current_word = chain.steps[-1].word if chain.steps else chain.start_word
    continuation = model.find_route(
        current_word, chain.target_word, exclude=exclude, win_threshold=chain.threshold, **_SEARCH_PARAMS
    )
    if continuation is not None:
        return continuation[0]

    if current_word != chain.start_word:
        fresh = model.find_route(
            chain.start_word, chain.target_word, exclude=exclude, win_threshold=chain.threshold, **_SEARCH_PARAMS
        )
        if fresh is not None:
            return fresh[0]

    return None


def _compute_solution_route(model, start_word, target_word, threshold):
    """Find the actual shortest real route the model can find between start
    and target at this threshold, computed once when the puzzle is created.
    Both par (score baseline) and the give-up reveal reuse this same route,
    rather than re-searching from wherever the player currently is — that
    re-searching was what produced disconnected/incomplete give-up routes.
    Tries a generous search first, then an even more expensive one before
    giving up. Returns the full path including start_word, or None."""
    route = model.find_route(start_word, target_word, win_threshold=threshold, **_PAR_SEARCH_PARAMS)
    if route is None:
        route = model.find_route(
            start_word, target_word, win_threshold=threshold, **_PAR_FALLBACK_SEARCH_PARAMS
        )
    return [start_word] + route if route is not None else None


def _apply_step_and_check_win(chain, step, conn):
    winning_connection = chain.winning_connection()
    won = winning_connection is not None
    saved_to_high_scores = False
    if won:
        if not chain.gave_up_before:
            save_attempt(conn, chain, player_name=session.get("player_name"))
            saved_to_high_scores = True
        chain.mark_won()
    return {
        "word": step.word,
        "neighbor_similarity": step.neighbor_similarity,
        "target_similarity": step.target_similarity,
        "is_digression": step.is_digression,
        "similarities": step.similarities,
        "winning_connection": winning_connection,
        "score": chain.score(),
        "par_length": chain.par_length,
        "words_used": len(chain.steps),
        "won": won,
        "saved_to_high_scores": saved_to_high_scores,
        "over_soft_cap": chain.is_over_soft_cap(),
    }


@bp.get("/")
def index():
    return current_app.send_static_file("index.html")


@bp.get("/scores")
def scores_page():
    return current_app.send_static_file("scores.html")


@bp.get("/api/health")
def health():
    return jsonify(status="ok")


@bp.get("/api/player_name")
def get_player_name():
    return jsonify(name=session.get("player_name"))


@bp.post("/api/player_name")
def set_player_name():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    name = payload.get("name", "").strip()[:_MAX_PLAYER_NAME_LENGTH] or None

    session.permanent = True
    session["player_name"] = name

    return jsonify(name=name)


@bp.post("/api/game/new")
def new_game():
    model = _get_model()
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    mode = payload.get("mode", "random")
    threshold = get_last_threshold(_get_db_conn())

    if mode == "manual":
        word1 = payload.get("word1", "").strip().lower()
        word2 = payload.get("word2", "").strip().lower()
        if not model.contains(word1):
            return jsonify(error=f"'{word1}' is not a recognized word"), 400
        if not model.contains(word2):
            return jsonify(error=f"'{word2}' is not a recognized word"), 400
        start_word, target_word = word1, word2
        solution_route = _compute_solution_route(model, start_word, target_word, threshold)
    else:
        start_word = target_word = None
        solution_route = None
        for _ in range(_PAR_REROLL_ATTEMPTS):
            start_word, target_word = model.random_pair()
            solution_route = _compute_solution_route(model, start_word, target_word, threshold)
            if solution_route is not None:
                break
        # If every reroll failed to find a route, the last-rolled pair is
        # kept and Chain.score() falls back to the legacy formula.

    par_length = len(solution_route) - 1 if solution_route is not None else None

    chain = Chain(
        model,
        start_word=start_word,
        target_word=target_word,
        threshold=threshold,
        par_length=par_length,
        solution_route=solution_route,
    )
    session["chain"] = chain.to_dict()

    return jsonify(
        start_word=start_word,
        target_word=target_word,
        start_target_similarity=chain.start_target_similarity(),
        threshold=chain.threshold,
        par_length=chain.par_length,
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
    chain.solution_route = _compute_solution_route(model, chain.start_word, chain.target_word, threshold)
    chain.par_length = len(chain.solution_route) - 1 if chain.solution_route is not None else None
    session["chain"] = chain.to_dict()
    set_last_threshold(_get_db_conn(), threshold)

    return jsonify(threshold=chain.threshold, par_length=chain.par_length)


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
    result = _apply_step_and_check_win(chain, step, _get_db_conn())
    session["chain"] = chain.to_dict()

    return jsonify(**result)


@bp.get("/api/game/hint_cost")
def hint_cost():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed:
        return jsonify(error="This game is already complete — start a new game."), 400

    return jsonify(cost=chain.next_hint_cost())


@bp.post("/api/game/hint")
def hint():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed:
        return jsonify(error="This game is already complete — start a new game."), 400

    hint_word = _find_hint_word(chain, model)
    if hint_word is None:
        return jsonify(
            hint_word=None,
            cost=0,
            score=chain.score(),
            par_length=chain.par_length,
            words_used=len(chain.steps),
        )

    cost = chain.use_hint()
    step = chain.add_word(hint_word)
    result = _apply_step_and_check_win(chain, step, _get_db_conn())
    session["chain"] = chain.to_dict()

    return jsonify(hint_word=hint_word, cost=cost, **result)


@bp.post("/api/game/give_up")
def give_up():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])

    if chain.completed:
        return jsonify(error="This game is already complete — start a new game."), 400

    best_step = chain.best_step()

    chain.mark_given_up()
    session["chain"] = chain.to_dict()

    return jsonify(
        given_up=True,
        best_word=best_step.word if best_step else None,
        best_similarity=best_step.target_similarity if best_step else None,
        route=chain.solution_route,
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
        par_length=chain.par_length,
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
