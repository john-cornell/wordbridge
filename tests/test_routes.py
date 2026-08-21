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
        "par_length": 1,  # "auto" is trivially within reach of "cat" in the tiny fixture vocab
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
    assert response.get_json() == {"threshold": 0.01}

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
        "error": "Can't restart a won game — start a new game instead."
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
        "par_length": 1,
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
        "error": "This game is already complete — start a new game."
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


def test_long_chain_does_not_overflow_session_cookie(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    # "car" is deliberately excluded here: it's highly similar to "auto" in
    # the tiny fixture model and would trigger an early win, short-circuiting
    # the chain before it reaches the length this test needs.
    #
    # The real-world bug report measured overflow at ~19 words against the
    # full word2vec vocabulary (longer words, more float precision per
    # entry). This fixture's vocabulary is tiny (3-4 letter words, only two
    # distinct words cycled), so the same O(n^2) payload is much smaller per
    # step and doesn't cross 4093 bytes until roughly 170+ steps. 200 steps
    # is used here instead of ~20 so this test is a genuine regression
    # guard: verified to fail (cookie > 4093 bytes) against the unfixed
    # code, and pass comfortably against the fix.
    words = ["dog", "cat"]
    response = None
    for i in range(200):
        response = client.post("/api/game/word", json={"word": words[i % len(words)]})
        assert response.status_code == 200

    set_cookie = response.headers.get("Set-Cookie", "")
    if set_cookie:
        assert len(set_cookie) < 4093
    else:
        # Flask doesn't necessarily resend Set-Cookie on every response, so
        # fall back to checking the size of the persisted session cookie
        # directly via the test client's cookie jar.
        session_cookie = client.get_cookie("session")
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
    client.post("/api/game/hint")

    peek = client.get("/api/game/hint_cost").get_json()
    assert peek == {"cost": 10}


def test_hint_never_suggests_a_word_already_on_the_board(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    # The target itself ("auto") is fair game for a first hint — it's the
    # destination, not something already played.
    first = client.post("/api/game/hint").get_json()
    assert first["hint_word"] != "cat"

    # Once played (by the first hint), it must not be suggested again.
    second = client.post("/api/game/hint").get_json()
    assert second["hint_word"] not in {"cat", first["hint_word"]}


def test_hint_reveals_next_word_and_charges_five_points(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    response = client.post("/api/game/hint")
    data = response.get_json()

    assert response.status_code == 200
    assert data["hint_word"] == "auto"
    assert data["cost"] == 5
    assert data["score"] == 33  # par 1: effective_words = 1 step + 2 for the hint -> 100*1/3
    # The hint is applied as a real move, not just suggested.
    assert data["word"] == "auto"


def test_hint_cost_doubles_on_repeated_use(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})

    first = client.post("/api/game/hint").get_json()
    second = client.post("/api/game/hint").get_json()

    assert first["cost"] == 5
    assert second["cost"] == 10
    # par 1: effective_words = 2 steps + 1 digression + 4 for two hints -> 100*1/7
    assert second["score"] == 14


def test_hint_falls_back_to_route_from_start_when_current_position_is_a_dead_end(
    client, tiny_model, monkeypatch
):
    real_find_route = tiny_model.find_route

    def fake_find_route(from_word, to_word, **kwargs):
        if from_word == "dog":
            return None  # wherever the player wandered to leads nowhere
        return real_find_route(from_word, to_word, **kwargs)

    monkeypatch.setattr(tiny_model, "find_route", fake_find_route)

    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/hint")
    data = response.get_json()

    assert response.status_code == 200
    assert data["hint_word"] == "auto"  # first step of a fresh route from "cat", not "dog"
    assert data["cost"] == 5


def test_hint_rejected_on_completed_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/give_up")

    response = client.post("/api/game/hint")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete — start a new game."
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

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["route"] == ["cat", "auto"]


def test_give_up_route_is_none_when_no_real_path_can_be_found_anywhere(
    client, tiny_model, monkeypatch
):
    # Every search strategy fails — give_up must not fall back to echoing
    # the player's own dead-end path as if it were a solution.
    monkeypatch.setattr(tiny_model, "find_route", lambda *args, **kwargs: None)
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["route"] is None


def test_give_up_falls_back_to_route_from_start_when_current_position_is_a_dead_end(
    client, tiny_model, monkeypatch
):
    real_find_route = tiny_model.find_route

    def fake_find_route(from_word, to_word, **kwargs):
        if from_word == "dog":
            return None  # wherever the player wandered to leads nowhere
        return real_find_route(from_word, to_word, **kwargs)

    monkeypatch.setattr(tiny_model, "find_route", fake_find_route)

    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    # A real route from the true start ("cat"), not the player's dead-end ("dog").
    assert data["route"] == ["cat", "auto"]


def test_give_up_route_includes_words_already_played(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})

    response = client.post("/api/game/give_up")
    data = response.get_json()

    assert response.status_code == 200
    assert data["route"] == ["cat", "dog", "auto"]


def test_give_up_locks_chain_against_further_add_word(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/give_up")

    response = client.post("/api/game/word", json={"word": "cat"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete — start a new game."
    }


def test_give_up_on_already_won_chain_returns_400(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.post("/api/game/give_up")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "This game is already complete — start a new game."
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


def test_clear_high_scores_empties_both_high_scores_and_history(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/threshold", json={"threshold": 0.05})
    client.post("/api/game/word", json={"word": "dog"})  # wins (bridges cat to auto)

    response = client.post("/api/high_scores/clear")

    assert response.status_code == 200
    assert response.get_json() == {"cleared": True}
    assert client.get("/api/high_scores").get_json() == {"scores": []}
    assert client.get("/api/history").get_json() == {"attempts": []}


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
