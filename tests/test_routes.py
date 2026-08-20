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
        "threshold": 0.7,
    }


def test_new_game_manual_mode_returns_start_target_similarity(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "auto"},
    )
    data = response.get_json()
    assert "start_target_similarity" in data


def test_add_word_without_active_game_returns_error(client):
    response = client.post("/api/game/word", json={"word": "dog"})
    assert response.status_code == 400


def test_add_word_progresses_chain_and_persists_on_win(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    response = client.post("/api/game/word", json={"word": "auto"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["won"] is True
    assert data["score"] == 90  # 100 - 10*1 - 5*0

    history_response = client.get("/api/history")
    attempts = history_response.get_json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["target_word"] == "auto"


def test_restart_clears_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "car"})
    response = client.post("/api/game/restart")
    assert response.get_json() == {
        "start_word": "cat",
        "target_word": "auto",
        "start_target_similarity": 0.0,
        "threshold": 0.7,
    }


def test_restart_returns_start_target_similarity(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "car"})
    response = client.post("/api/game/restart")
    data = response.get_json()
    assert "start_target_similarity" in data


def test_add_word_after_win_returns_400_and_does_not_add_second_history_row(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "auto"})  # wins immediately

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
    client.post("/api/game/word", json={"word": "auto"})  # wins

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
    assert data["route"] == ["auto"]


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
    client.post("/api/game/word", json={"word": "car"})  # wins immediately (sim ~0.99)

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


def test_restart_after_give_up_produces_fresh_playable_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "dog"})
    client.post("/api/game/give_up")

    restart_response = client.post("/api/game/restart")
    assert restart_response.status_code == 200

    add_response = client.post("/api/game/word", json={"word": "dog"})
    assert add_response.status_code == 200
