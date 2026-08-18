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
    assert response.get_json() == {"start_word": "cat", "target_word": "auto"}


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
    assert response.get_json() == {"start_word": "cat", "target_word": "auto"}


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
