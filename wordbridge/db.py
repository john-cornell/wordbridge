import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_word TEXT NOT NULL,
    target_word TEXT NOT NULL,
    chain_json TEXT NOT NULL,
    num_digressions INTEGER NOT NULL,
    score INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    player_name TEXT
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_threshold REAL NOT NULL
);
"""

DEFAULT_THRESHOLD = 0.5


def init_db(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(SCHEMA)
    try:
        # Migration for databases created before player_name existed —
        # CREATE TABLE IF NOT EXISTS above is a no-op on an existing table,
        # so older attempts tables need the column added explicitly.
        conn.execute("ALTER TABLE attempts ADD COLUMN player_name TEXT")
    except sqlite3.OperationalError:
        pass  # column already present
    conn.commit()
    return conn


def get_last_threshold(conn):
    row = conn.execute("SELECT last_threshold FROM preferences WHERE id = 1").fetchone()
    return row[0] if row else DEFAULT_THRESHOLD


def set_last_threshold(conn, threshold):
    conn.execute(
        "INSERT INTO preferences (id, last_threshold) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_threshold = excluded.last_threshold",
        (threshold,),
    )
    conn.commit()


def save_attempt(conn, chain, player_name=None):
    conn.execute(
        """
        INSERT INTO attempts (start_word, target_word, chain_json, num_digressions, score, created_at, player_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chain.start_word,
            chain.target_word,
            json.dumps([step.word for step in chain.steps]),
            chain.num_digressions(),
            chain.score(),
            datetime.now(timezone.utc).isoformat(),
            player_name,
        ),
    )
    conn.commit()


def list_high_scores(conn, limit=50):
    rows = conn.execute(
        "SELECT id, start_word, target_word, score, created_at, player_name "
        "FROM attempts ORDER BY score DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": row[0],
            "start_word": row[1],
            "target_word": row[2],
            "score": row[3],
            "created_at": row[4],
            "player_name": row[5],
        }
        for row in rows
    ]


def clear_attempts(conn):
    conn.execute("DELETE FROM attempts")
    conn.commit()


def list_attempts(conn):
    rows = conn.execute(
        "SELECT id, start_word, target_word, chain_json, num_digressions, score, created_at, player_name "
        "FROM attempts ORDER BY id DESC"
    ).fetchall()
    return [
        {
            "id": row[0],
            "start_word": row[1],
            "target_word": row[2],
            "chain": json.loads(row[3]),
            "num_digressions": row[4],
            "score": row[5],
            "created_at": row[6],
            "player_name": row[7],
        }
        for row in rows
    ]
