import threading

from wordbridge.db import (
    clear_attempts,
    get_attempt_for_replay,
    get_last_threshold,
    init_db,
    list_attempts,
    list_high_scores,
    save_attempt,
    set_last_threshold,
)
from wordbridge.game import Chain


def test_init_db_creates_attempts_table():
    conn = init_db(":memory:")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='attempts'"
    )
    assert cursor.fetchone() is not None


def test_get_last_threshold_defaults_when_never_set():
    conn = init_db(":memory:")
    assert get_last_threshold(conn) == 0.5


def test_set_last_threshold_then_get_returns_it():
    conn = init_db(":memory:")
    set_last_threshold(conn, 0.42)
    assert get_last_threshold(conn) == 0.42


def test_set_last_threshold_overwrites_previous_value():
    conn = init_db(":memory:")
    set_last_threshold(conn, 0.3)
    set_last_threshold(conn, 0.9)
    assert get_last_threshold(conn) == 0.9


def test_save_and_list_attempt(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")

    save_attempt(conn, chain)
    attempts = list_attempts(conn)

    assert len(attempts) == 1
    assert attempts[0]["start_word"] == "cat"
    assert attempts[0]["target_word"] == "auto"
    assert attempts[0]["chain"] == ["dog"]
    assert attempts[0]["score"] == chain.score()


def test_save_attempt_stores_player_name(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")

    save_attempt(conn, chain, player_name="Alice")

    assert list_attempts(conn)[0]["player_name"] == "Alice"
    assert list_high_scores(conn)[0]["player_name"] == "Alice"


def test_save_attempt_without_player_name_defaults_to_none(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")

    save_attempt(conn, chain)

    assert list_attempts(conn)[0]["player_name"] is None


def test_init_db_migrates_an_existing_table_without_player_name_column(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "legacy.db")

    # Build a database with the pre-player_name schema, as if created by an
    # older version of this app.
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.execute(
        """
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_word TEXT NOT NULL,
            target_word TEXT NOT NULL,
            chain_json TEXT NOT NULL,
            num_digressions INTEGER NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    legacy_conn.execute(
        "INSERT INTO attempts (start_word, target_word, chain_json, num_digressions, score, created_at) "
        "VALUES ('cat', 'auto', '[]', 0, 100, '2026-01-01T00:00:00')"
    )
    legacy_conn.commit()
    legacy_conn.close()

    # init_db must not crash against this older schema, and must add the
    # missing column so existing rows remain readable.
    conn = init_db(db_path)
    attempts = list_attempts(conn)

    assert len(attempts) == 1
    assert attempts[0]["player_name"] is None


def test_connection_can_be_used_across_threads(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")

    def save_from_background_thread():
        save_attempt(conn, chain)

    thread = threading.Thread(target=save_from_background_thread)
    thread.start()
    thread.join()

    attempts = list_attempts(conn)
    assert len(attempts) == 1
    assert attempts[0]["start_word"] == "cat"
    assert attempts[0]["target_word"] == "auto"


def test_list_high_scores_orders_by_score_descending(tiny_model):
    conn = init_db(":memory:")
    low = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    low.add_word("dog")
    low.add_word("car")
    save_attempt(conn, low)  # 2 steps, score 80

    high = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    high.add_word("dog")
    save_attempt(conn, high)  # 1 step, score 90

    scores = list_high_scores(conn)

    assert [entry["score"] for entry in scores] == [90, 80]
    assert scores[0]["start_word"] == "cat"
    assert scores[0]["target_word"] == "auto"
    assert scores[0]["threshold"] == 0.5
    assert "created_at" in scores[0]


def test_clear_attempts_empties_the_table(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")
    save_attempt(conn, chain)

    clear_attempts(conn)

    assert list_attempts(conn) == []
    assert list_high_scores(conn) == []


def test_save_attempt_stores_threshold_for_replay(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")

    save_attempt(conn, chain)
    attempt_id = list_attempts(conn)[0]["id"]

    assert get_attempt_for_replay(conn, attempt_id) == (
        "cat",
        "auto",
        0.5,
        [{"word": "dog", "is_hint": False}],
    )
    assert list_high_scores(conn)[0]["has_solution"] is True


def test_save_attempt_stores_is_hint_per_step(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.11)
    chain.add_word("dog")
    chain.add_word("car", is_hint=True)

    save_attempt(conn, chain)
    attempt_id = list_attempts(conn)[0]["id"]

    _, _, _, steps = get_attempt_for_replay(conn, attempt_id)
    assert steps == [
        {"word": "dog", "is_hint": False},
        {"word": "car", "is_hint": True},
    ]


def test_get_attempt_for_replay_returns_none_for_unknown_id():
    conn = init_db(":memory:")
    assert get_attempt_for_replay(conn, 999) is None


def test_init_db_migrates_an_existing_table_without_threshold_column(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "legacy_no_threshold.db")

    # Build a database with the pre-solution-reveal schema, as if created by
    # an older version of this app (has player_name, but not the threshold
    # column added for the high-scores reveal).
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.execute(
        """
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_word TEXT NOT NULL,
            target_word TEXT NOT NULL,
            chain_json TEXT NOT NULL,
            num_digressions INTEGER NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            player_name TEXT
        )
        """
    )
    legacy_conn.execute(
        "INSERT INTO attempts (start_word, target_word, chain_json, num_digressions, score, created_at, player_name) "
        "VALUES ('cat', 'auto', '[]', 0, 100, '2026-01-01T00:00:00', NULL)"
    )
    legacy_conn.commit()
    legacy_conn.close()

    conn = init_db(db_path)
    attempts = list_attempts(conn)

    assert len(attempts) == 1
    assert list_high_scores(conn)[0]["has_solution"] is False
    start_word, target_word, threshold, words = get_attempt_for_replay(conn, attempts[0]["id"])
    assert (start_word, target_word, threshold, words) == ("cat", "auto", None, [])


def test_get_attempt_for_replay_normalizes_old_flat_string_chain_json(tmp_path):
    # Rows saved between the threshold column existing and is_hint being
    # tracked per-step have a real threshold but chain_json as a flat list
    # of word strings, not {"word", "is_hint"} dicts.
    db_path = str(tmp_path / "in_between.db")
    conn = init_db(db_path)
    conn.execute(
        "INSERT INTO attempts (start_word, target_word, chain_json, num_digressions, score, created_at, threshold) "
        "VALUES ('cat', 'auto', '[\"dog\", \"car\"]', 0, 100, '2026-01-01T00:00:00', 0.11)"
    )
    conn.commit()
    attempt_id = list_attempts(conn)[0]["id"]

    assert get_attempt_for_replay(conn, attempt_id) == (
        "cat",
        "auto",
        0.11,
        [{"word": "dog", "is_hint": False}, {"word": "car", "is_hint": False}],
    )


def test_list_attempts_orders_most_recent_first(tiny_model):
    conn = init_db(":memory:")
    first = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    first.add_word("dog")
    save_attempt(conn, first)

    second = Chain(tiny_model, start_word="car", target_word="dog", threshold=0.01)
    second.add_word("cat")
    save_attempt(conn, second)

    attempts = list_attempts(conn)
    assert attempts[0]["start_word"] == "car"
    assert attempts[1]["start_word"] == "cat"
