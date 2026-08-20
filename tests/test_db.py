import threading

from wordbridge.db import (
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
    assert get_last_threshold(conn) == 0.7


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
    chain.add_word("auto")

    save_attempt(conn, chain)
    attempts = list_attempts(conn)

    assert len(attempts) == 1
    assert attempts[0]["start_word"] == "cat"
    assert attempts[0]["target_word"] == "auto"
    assert attempts[0]["chain"] == ["auto"]
    assert attempts[0]["score"] == chain.score()


def test_connection_can_be_used_across_threads(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("auto")

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
    assert "created_at" in scores[0]


def test_list_attempts_orders_most_recent_first(tiny_model):
    conn = init_db(":memory:")
    first = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    first.add_word("auto")
    save_attempt(conn, first)

    second = Chain(tiny_model, start_word="car", target_word="dog", threshold=0.01)
    second.add_word("dog")
    save_attempt(conn, second)

    attempts = list_attempts(conn)
    assert attempts[0]["start_word"] == "car"
    assert attempts[1]["start_word"] == "cat"
