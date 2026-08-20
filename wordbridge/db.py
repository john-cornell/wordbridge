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
    created_at TEXT NOT NULL
);
"""


def init_db(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def save_attempt(conn, chain):
    conn.execute(
        """
        INSERT INTO attempts (start_word, target_word, chain_json, num_digressions, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            chain.start_word,
            chain.target_word,
            json.dumps([step.word for step in chain.steps]),
            chain.num_digressions(),
            chain.score(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def list_high_scores(conn, limit=50):
    rows = conn.execute(
        "SELECT id, start_word, target_word, score, created_at "
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
        }
        for row in rows
    ]


def list_attempts(conn):
    rows = conn.execute(
        "SELECT id, start_word, target_word, chain_json, num_digressions, score, created_at "
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
        }
        for row in rows
    ]
