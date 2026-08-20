import threading

from wordbridge.db import init_db, list_attempts, save_attempt
from wordbridge.game import Chain


def test_init_db_creates_attempts_table():
    conn = init_db(":memory:")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='attempts'"
    )
    assert cursor.fetchone() is not None


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


def test_list_attempts_orders_most_recent_first(tiny_model):
    conn = init_db(":memory:")
    first = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    first.add_word("dog")
    save_attempt(conn, first)

    second = Chain(tiny_model, start_word="car", target_word="dog", threshold=0.01)
    second.add_word("dog")
    save_attempt(conn, second)

    attempts = list_attempts(conn)
    assert attempts[0]["start_word"] == "car"
    assert attempts[1]["start_word"] == "cat"
