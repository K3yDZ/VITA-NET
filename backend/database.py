"""SQLite persistence — astronauts + vitals_log + alerts_log + mission_events."""

import logging
import sqlite3
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("lifeline.database")

DB_PATH = Path(__file__).parent / "vitanet.db"

# Seeded astronaut IDs (from ARTEMIS_ROSTER in main.py, first CREW_SIZE entries)
# This is the ORIGINAL seeded roster, not the dynamically modified ROSTER_IDS global.
# Import inside function to avoid circular import at module load time.
def _get_seeded_ids() -> set[str]:
    """Get the original seeded astronaut IDs from the roster definition."""
    try:
        from main import ARTEMIS_ROSTER, CREW_SIZE
        return {a.id for a in ARTEMIS_ROSTER[:CREW_SIZE]}
    except Exception:
        # Fallback to default roster (CREW_SIZE=6)
        return {"a1", "a2", "a3", "a4", "a5", "a6"}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        # astronauts
        conn.execute("""
            CREATE TABLE IF NOT EXISTS astronauts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Crew Member',
                baseline_hr REAL,
                baseline_bp_sys REAL,
                baseline_bp_dia REAL,
                baseline_spo2 REAL,
                baseline_temp REAL,
                baseline_stress REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # vitals_log
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vitals_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                astronaut_id TEXT NOT NULL,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                heart_rate REAL,
                bp_sys REAL,
                bp_dia REAL,
                spo2 REAL,
                temp_c REAL,
                stress_index REAL,
                radiation_msv REAL,
                hrv REAL,
                FOREIGN KEY (astronaut_id) REFERENCES astronauts(id)
            )
        """)
        # try add hrv column if missing (migration)
        try:
            conn.execute("ALTER TABLE vitals_log ADD COLUMN hrv REAL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE astronauts ADD COLUMN dossier TEXT")
        except Exception:
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vitals_astronaut_ts ON vitals_log (astronaut_id, ts)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                astronaut_id TEXT NOT NULL,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                level TEXT,
                metric TEXT,
                value REAL,
                message TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mission_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                event_type TEXT,
                description TEXT
            )
        """)


def insert_reading(astronaut_id: str, v) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO vitals_log
                (astronaut_id, heart_rate, bp_sys, bp_dia, spo2, temp_c, stress_index, radiation_msv, hrv)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (astronaut_id, v.heartRate, v.bpSys, v.bpDia, v.spo2, v.tempC, v.stressIndex, v.radiationMSv, getattr(v, "hrv", None)),
        )


def get_history(astronaut_id: str, limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vitals_log WHERE astronaut_id = ? ORDER BY ts DESC LIMIT ?",
            (astronaut_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def list_astronauts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM astronauts ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def upsert_astronaut(astronaut_id: str, name: str, role: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO astronauts (id, name, role) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role""",
            (astronaut_id, name, role),
        )


def delete_astronaut(astronaut_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM astronauts WHERE id = ?", (astronaut_id,))
        conn.execute("DELETE FROM vitals_log WHERE astronaut_id = ?", (astronaut_id,))


def get_all_astronaut_ids() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT astronaut_id FROM vitals_log").fetchall()
        return [dict(r) for r in rows]


def log_alert(astronaut_id: str, level: str, metric: str, value: float, message: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts_log (astronaut_id, level, metric, value, message) VALUES (?, ?, ?, ?, ?)",
            (astronaut_id, level, metric, value, message),
        )


def reset_all() -> None:
    """Reset all data to safe state - clears logs and removes non-seeded astronauts."""
    seeded_ids = _get_seeded_ids()
    with get_conn() as conn:
        # Clear all logs
        conn.execute("DELETE FROM vitals_log")
        conn.execute("DELETE FROM alerts_log")
        conn.execute("DELETE FROM mission_events")
        # Remove any astronaut not in the seeded roster (malicious/injected records)
        placeholders = ",".join("?" for _ in seeded_ids)
        conn.execute(f"DELETE FROM astronauts WHERE id NOT IN ({placeholders})", tuple(seeded_ids))
        log.info("All data reset to safe state; non-seeded astronauts removed")
