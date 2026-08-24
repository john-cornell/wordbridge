import pytest


def test_new_game_random_mode_returns_word_pair(client):
    response = client.post("/api/game/new", json={"mode": "random"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["start_word"] != data["target_word"]


def test_new_game_manual_mode_rejects_unknown_word(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "nonexistent"},
    )
    assert response.status_code == 400


def test_new_game_manual_mode_accepts_known_words(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "auto"},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "start_word": "cat",
        "target_word": "auto",
        "start_target_similarity": 0.0,
        "threshold": 0.5,
        "par_length": None,  # cat's and auto's components don't connect at all at the default 0.5 threshold
    }


def test_new_game_manual_mode_rejects_identical_words(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "cat"},
    )
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Start and target words must be different"
    }


def test_new_game_manual_mode_reports_all_failing_validations_at_once(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "nonexistent1", "word2": "nonexistent2"},
    )
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "'nonexistent1' is not a recognized word\n'nonexistent2' is not a recognized word"
    }


def test_new_game_manual_mode_dedupes_identical_invalid_word_repeated_in_both_boxes(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "nonexistent", "word2": "nonexistent"},
    )
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "'nonexistent' is not a recognized word\nStart and target words must be different"
    }


def test_new_game_manual_mode_returns_start_target_similarity(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "auto"},
    )
    data = response.get_json()
    assert "start_target_similarity" in data


def test_set_threshold_without_active_game_returns_error(client):
    response = client.post("/api/game/threshold", json={"threshold": 0.5})
    assert response.status_code == 400


def test_set_threshold_updates_chain_before_any_word_added(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    response = client.post("/api/game/threshold", json={"threshold": 0.01})

    assert response.status_code == 200
    assert response.get_json() == {"threshold": 0.01, "par_length": 2}

    # A threshold this low should now make even a weak similarity a win.
    word_response = client.post("/api/game/word", json={"word": "dog"})
    assert word_response.get_json()["won"] is True


def test_set_threshold_rejected_after_first_word_added(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/threshold", json={"threshold": 0.01})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Threshold is locked once the game has started."
    }


def test_set_threshold_rejects_out_of_range_value(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    response = client.post("/api/game/threshold", json={"threshold": 1.5})

    assert response.status_code == 400


def test_new_game_defaults_threshold_to_last_saved_value(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.42})

    response = client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    assert response.get_json()["threshold"] == 0.42


def test_add_word_without_active_game_returns_error(client):
    response = client.post("/api/game/word", json={"word": "dog"})
    assert response.status_code == 400


def test_add_word_progresses_chain_and_persists_on_win(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    # threshold=0.05: cat-dog and dog-auto both clear it, so "dog" bridges
    # start to target and wins even though cat-auto direct similarity is ~0.0.
    response = client.post("/api/game/word", json={"word": "dog"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["won"] is True
    assert data["score"] == 100  # par 1, 1 word used, no digressions/hints -> 100*1/1
    assert data["winning_connection"] == [
        {"a": "cat", "b": "dog", "similarity": pytest.approx(0.9939, abs=0.001)},
        {"a": "dog", "b": "auto", "similarity": pytest.approx(0.1098, abs=0.001)},
    ]

    history_response = client.get("/api/history")
    attempts = history_response.get_json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["target_word"] == "auto"


def test_restart_after_win_is_rejected(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.post("/api/game/restart")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Can't restart a won game. Start a new game instead."
    }


def test_restart_clears_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "car"})
    response = client.post("/api/game/restart")
    assert response.get_json() == {
        "start_word": "cat",
        "target_word": "auto",
        "start_target_similarity": 0.0,
        "threshold": 0.5,
        "par_length": None,
    }


def test_restart_returns_start_target_similarity(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "car"})
    response = client.post("/api/game/restart")
    data = response.get_json()
    assert "start_target_similarity" in data


def test_add_word_after_win_returns_400_and_does_not_add_second_history_row(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.post("/api/game/word", json={"word": "car"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete. Start a new game instead."
    }

    history_response = client.get("/api/history")
    attempts = history_response.get_json()["attempts"]
    assert len(attempts) == 1


def test_only_one_history_row_after_repeated_add_word_calls_post_win(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    for _ in range(3):
        client.post("/api/game/word", json={"word": "car"})

    history_response = client.get("/api/history")
    attempts = history_response.get_json()["attempts"]
    assert len(attempts) == 1


def test_new_game_with_non_dict_json_body_does_not_500(client):
    response = client.post(
        "/api/game/new", data='"hello"', content_type="application/json"
    )
    assert response.status_code < 500


def test_add_word_with_non_dict_json_body_does_not_500(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    response = client.post(
        "/api/game/word", data='"hello"', content_type="application/json"
    )
    assert response.status_code < 500


def test_add_word_response_includes_similarities_to_other_chain_words(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    response1 = client.post("/api/game/word", json={"word": "dog"})
    # First call should still be in progress
    assert response1.status_code == 200
    response2 = client.post("/api/game/word", json={"word": "car"})
    data = response2.get_json()

    # The second word should have similarities to cat, auto, and dog
    assert "similarities" in data
    words_compared = {entry["word"] for entry in data["similarities"]}
    assert words_compared == {"cat", "auto", "dog"}

    # "car" only connects to "auto" here (an island) — not a win, so no connection.
    assert data["won"] is False
    assert data["winning_connection"] is None


def test_long_chain_does_not_overflow_session_cookie(big_vocab_client, big_vocab_model):
    big_vocab_client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    # Words can no longer be replayed, so this test uses a fixture with 200+
    # mutually-orthogonal filler words (similarity 0.0 to everything) instead
    # of cycling a couple of words — that also guarantees no accidental win.
    #
    # The real-world bug report measured overflow at ~19 words against the
    # full word2vec vocabulary. 200 steps is used here as a comfortable
    # regression guard: verified to fail (cookie > 4093 bytes) against the
    # unfixed code, and pass comfortably against the fix.
    filler_words = [w for w in big_vocab_model._filtered_vocab if w not in ("cat", "auto")]
    response = None
    for i in range(200):
        response = big_vocab_client.post("/api/game/word", json={"word": filler_words[i]})
        assert response.status_code == 200

    set_cookie = response.headers.get("Set-Cookie", "")
    if set_cookie:
        assert len(set_cookie) < 4093
    else:
        # Flask doesn't necessarily resend Set-Cookie on every response, so
        # fall back to checking the size of the persisted session cookie
        # directly via the test client's cookie jar.
        session_cookie = big_vocab_client.get_cookie("session")
        assert session_cookie is not None
        assert len(session_cookie.value) < 4093


def test_hint_without_active_game_returns_error(client):
    response = client.post("/api/game/hint")
    assert response.status_code == 400


def test_hint_cost_without_active_game_returns_error(client):
    response = client.get("/api/game/hint_cost")
    assert response.status_code == 400


def test_hint_cost_peeks_without_charging_or_applying_anything(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    first_peek = client.get("/api/game/hint_cost").get_json()
    second_peek = client.get("/api/game/hint_cost").get_json()

    assert first_peek == {"cost": 5}
    assert second_peek == {"cost": 5}  # unchanged — peeking never charges

    history_response = client.get("/api/history").get_json()
    assert history_response == {"attempts": []}


def test_hint_cost_reflects_escalating_price_after_a_real_hint(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})
    client.post("/api/game/hint")

    peek = client.get("/api/game/hint_cost").get_json()
    assert peek == {"cost": 10}


def test_hint_never_suggests_a_word_already_on_the_board(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})

    first = client.post("/api/game/hint").get_json()
    assert first["hint_word"] != "cat"

    # Once played (by the first hint), it must not be suggested again.
    second = client.post("/api/game/hint").get_json()
    assert second["hint_word"] not in {"cat", first["hint_word"]}


def test_hint_reveals_next_word_and_charges_five_points(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    # 0.11 sits between dog-auto (~0.1098, must stay disconnected) and
    # dog-car (~0.1104, must connect) — the only threshold in this fixture
    # where a genuine multi-hop route (cat->dog->car->auto) exists without
    # an instant win via dog alone.
    client.post("/api/game/threshold", json={"threshold": 0.11})

    response = client.post("/api/game/hint")
    data = response.get_json()

    assert response.status_code == 200
    # "dog" is the real first hop of the threshold-respecting route now —
    # not "auto" (the old rank-only bug jumped straight to the literal
    # target even though cat-auto has zero actual similarity).
    assert data["hint_word"] == "dog"
    assert data["cost"] == 5
    assert data["score"] == 100  # par 3 (cat->dog->car->auto): 1 step + 2 for the hint -> 100*3/3
    # The hint is applied as a real move, not just suggested.
    assert data["word"] == "dog"


def test_hint_cost_doubles_on_repeated_use(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})

    first = client.post("/api/game/hint").get_json()
    second = client.post("/api/game/hint").get_json()

    assert first["cost"] == 5
    assert second["hint_word"] == "car"
    assert second["cost"] == 10
    # par 3: effective_words = 2 steps + 0 digressions + 4 for two hints -> 100*3/6
    assert second["score"] == 50


def test_hint_rejected_on_completed_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/give_up")

    response = client.post("/api/game/hint")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete. Start a new game instead."
    }


def test_give_up_without_active_game_returns_error(client):
    response = client.post("/api/game/give_up")
    assert response.status_code == 400


def test_give_up_with_zero_steps_returns_null_best(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["given_up"] is True
    assert data["best_word"] is None
    assert data["best_similarity"] is None


def test_give_up_returns_best_word_and_similarity(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["best_word"] == "dog"
    assert data["best_similarity"] == pytest.approx(0.1098, abs=0.001)


def test_give_up_response_includes_route_to_target(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["route"] == ["cat", "dog", "car", "auto"]


def test_give_up_route_is_none_when_no_real_path_can_be_found_anywhere(
    client, tiny_model, monkeypatch
):
    # No route can be established when the puzzle is created — give_up must
    # reveal that honestly rather than echo the player's own dead-end path
    # as if it were a solution.
    monkeypatch.setattr(tiny_model, "find_route", lambda *args, **kwargs: None)
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["route"] is None


def test_give_up_route_is_the_precomputed_solution_regardless_of_what_was_played(client):
    # The give-up route is decided once, when the puzzle is created — it's
    # not re-derived from wherever the player actually wandered to. Playing
    # a word that ISN'T part of that route must not change what's revealed.
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})
    client.post("/api/game/word", json={"word": "car"})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["route"] == ["cat", "dog", "car", "auto"]


def test_give_up_locks_chain_against_further_add_word(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/give_up")

    response = client.post("/api/game/word", json={"word": "cat"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete. Start a new game instead."
    }


def test_give_up_on_already_won_chain_returns_400(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.post("/api/game/give_up")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete. Start a new game instead."
    }


def test_give_up_does_not_persist_to_history(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/give_up")

    history_response = client.get("/api/history")
    attempts = history_response.get_json()["attempts"]
    assert attempts == []


def test_high_scores_empty_when_no_wins_yet(client):
    response = client.get("/api/high_scores")
    assert response.status_code == 200
    assert response.get_json() == {"scores": []}


def test_high_scores_includes_win_with_source_dest_score_and_date(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.get("/api/high_scores")
    data = response.get_json()

    assert response.status_code == 200
    assert len(data["scores"]) == 1
    entry = data["scores"][0]
    assert entry["start_word"] == "cat"
    assert entry["target_word"] == "auto"
    assert entry["score"] == 100  # par 1, 1 word used, no digressions/hints -> 100*1/1
    assert "created_at" in entry
    assert entry["player_name"] is None


def test_high_scores_includes_the_player_name_set_before_winning(client):
    client.post("/api/player_name", json={"name": "Alice"})
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins

    entry = client.get("/api/high_scores").get_json()["scores"][0]
    assert entry["player_name"] == "Alice"


def test_high_scores_includes_has_solution_flag(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins

    entry = client.get("/api/high_scores").get_json()["scores"][0]
    assert entry["has_solution"] is True


def test_high_score_solution_replays_every_played_word_and_the_winning_bridge(client):
    # cat-dog-car-auto only connects at 0.11 once BOTH dog and car are
    # played, in that order (dog-auto alone isn't close enough) - a real
    # two-word bridge, not a single lucky word.
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/word", json={"word": "car"})  # wins

    attempt_id = client.get("/api/high_scores").get_json()["scores"][0]["id"]
    response = client.get(f"/api/high_scores/{attempt_id}/solution")
    data = response.get_json()

    assert response.status_code == 200
    assert data["available"] is True
    assert data["start_word"] == "cat"
    assert data["target_word"] == "auto"
    # "Full search" - every word actually played, not just the solver's
    # own idea of a route.
    assert [step["word"] for step in data["steps"]] == ["dog", "car"]
    # "Direct path" - only the winning bridge the player actually made.
    assert [link["a"] for link in data["winning_connection"]] == ["cat", "dog", "car"]
    assert [link["b"] for link in data["winning_connection"]] == ["dog", "car", "auto"]
    assert data["threshold"] == 0.11


def test_high_score_solution_marks_which_words_were_hints(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.11})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/hint")  # picks "car" and wins, per the bridge above

    attempt_id = client.get("/api/high_scores").get_json()["scores"][0]["id"]
    data = client.get(f"/api/high_scores/{attempt_id}/solution").get_json()

    is_hint_by_word = {step["word"]: step["is_hint"] for step in data["steps"]}
    assert is_hint_by_word == {"dog": False, "car": True}


def test_high_score_solution_returns_404_for_unknown_id(client):
    response = client.get("/api/high_scores/999/solution")
    assert response.status_code == 404


def test_high_score_solution_unavailable_for_attempts_predating_this_feature(app, client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins

    attempt_id = client.get("/api/high_scores").get_json()["scores"][0]["id"]

    # Simulate an attempt saved before the threshold column existed - it's
    # not otherwise recoverable, so the game can't be replayed correctly.
    with app.app_context():
        from wordbridge.routes import _get_db_conn

        conn = _get_db_conn()
        conn.execute("UPDATE attempts SET threshold = NULL WHERE id = ?", (attempt_id,))
        conn.commit()

    entry = client.get("/api/high_scores").get_json()["scores"][0]
    assert entry["has_solution"] is False

    response = client.get(f"/api/high_scores/{attempt_id}/solution")
    assert response.status_code == 200
    assert response.get_json() == {"available": False}


def test_get_player_name_defaults_to_null(client):
    response = client.get("/api/player_name")
    assert response.get_json() == {"name": None}


def test_set_player_name_then_get_returns_it(client):
    response = client.post("/api/player_name", json={"name": "  Bob  "})
    assert response.get_json() == {"name": "Bob"}
    assert client.get("/api/player_name").get_json() == {"name": "Bob"}


def test_set_player_name_truncates_overly_long_names(client):
    response = client.post("/api/player_name", json={"name": "x" * 50})
    assert response.get_json() == {"name": "x" * 30}


def test_set_player_name_to_blank_clears_it(client):
    client.post("/api/player_name", json={"name": "Bob"})
    response = client.post("/api/player_name", json={"name": "   "})
    assert response.get_json() == {"name": None}
    assert client.get("/api/player_name").get_json() == {"name": None}


def test_clear_high_scores_empties_both_high_scores_and_history(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.post("/api/high_scores/clear", json={"password": "deleteme"})

    assert response.status_code == 200
    assert response.get_json() == {"cleared": True}
    assert client.get("/api/high_scores").get_json() == {"scores": []}
    assert client.get("/api/history").get_json() == {"attempts": []}


def test_clear_high_scores_rejects_wrong_password(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins

    response = client.post("/api/high_scores/clear", json={"password": "wrong"})

    assert response.status_code == 403
    assert len(client.get("/api/high_scores").get_json()["scores"]) == 1


def test_clear_high_scores_rejects_missing_password(client):
    response = client.post("/api/high_scores/clear", json={})
    assert response.status_code == 403


def test_win_after_restart_following_give_up_is_not_saved_as_high_score(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/give_up")  # give up before playing any words
    client.post("/api/game/restart")

    response = client.post("/api/game/word", json={"word": "dog"})  # wins again
    data = response.get_json()

    assert data["won"] is True
    assert data["saved_to_high_scores"] is False
    assert client.get("/api/high_scores").get_json() == {"scores": []}
    assert client.get("/api/history").get_json() == {"attempts": []}


def test_win_without_prior_give_up_is_saved_as_high_score(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})

    response = client.post("/api/game/word", json={"word": "dog"})  # wins
    data = response.get_json()

    assert data["won"] is True
    assert data["saved_to_high_scores"] is True
    assert len(client.get("/api/high_scores").get_json()["scores"]) == 1


def test_restart_after_give_up_produces_fresh_playable_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/give_up")

    restart_response = client.post("/api/game/restart")
    assert restart_response.status_code == 200

    add_response = client.post("/api/game/word", json={"word": "dog"})
    assert add_response.status_code == 200
