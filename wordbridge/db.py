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
    player_name TEXT,
    solution_route_json TEXT,
    solution_trace_json TEXT
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
    for column in ("solution_route_json", "solution_trace_json"):
        try:
            # Same migration pattern, for attempts saved before the
            # high-scores "show solution" reveal existed — those rows keep
            # NULL here and the reveal is simply unavailable for them.
            conn.execute(f"ALTER TABLE attempts ADD COLUMN {column} TEXT")
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
        INSERT INTO attempts (
            start_word, target_word, chain_json, num_digressions, score, created_at, player_name,
            solution_route_json, solution_trace_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chain.start_word,
            chain.target_word,
            json.dumps([step.word for step in chain.steps]),
            chain.num_digressions(),
            chain.score(),
            datetime.now(timezone.utc).isoformat(),
            player_name,
            json.dumps(chain.solution_route) if chain.solution_route is not None else None,
            json.dumps(chain.solution_trace) if chain.solution_trace is not None else None,
        ),
    )
    conn.commit()


def list_high_scores(conn, limit=50):
    rows = conn.execute(
        "SELECT id, start_word, target_word, score, created_at, player_name, "
        "solution_route_json IS NOT NULL "
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
            "has_solution": bool(row[6]),
        }
        for row in rows
    ]


def get_attempt_solution(conn, attempt_id):
    """Returns (solution_route, solution_trace) for the high-scores "show
    solution" reveal, or None if no attempt with this id exists. Either or
    both of the pair can be None themselves — an attempt saved before this
    feature existed, or a puzzle with no findable route."""
    row = conn.execute(
        "SELECT solution_route_json, solution_trace_json FROM attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()
    if row is None:
        return None
    solution_route = json.loads(row[0]) if row[0] is not None else None
    solution_trace = json.loads(row[1]) if row[1] is not None else None
    return solution_route, solution_trace


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
