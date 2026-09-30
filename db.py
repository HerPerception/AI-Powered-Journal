"""Database connection and schema migrations.

This replaces `connect_db()` in app.py, which ran `CREATE TABLE IF NOT EXISTS`
on every request. That works exactly once. The moment you need a *second* schema
version there is nothing to run -- the table already exists, so the statement
no-ops and your new column never appears. `PRAGMA user_version` is SQLite's
built-in schema version counter, there for exactly this.

Two other changes, both required by what is coming:

**WAL mode.** Connections had no concurrency settings, which is fine for one
user and one process. It is not fine for gunicorn workers plus a background
analysis worker writing the same file -- SQLite starts returning
"database is locked". WAL lets readers proceed alongside one writer, and
`busy_timeout` makes a blocked writer wait its turn instead of failing.

**`row_factory = sqlite3.Row`.** Rows can now be read by column *name*.
`index.html` currently does `each_entry[2]` -- a positional index into
`SELECT *`, which is the fragility flagged in CONCEPTS.md and SESSION_NOTES 8.2.
Row supports position *and* name, so the template keeps working while we migrate
it. Doing this now, with three rows in the database, is the cheap moment.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

DB_PATH = "journal.db"


# --------------------------------------------------------------------------
# Migrations
#
# Each migration is a function that takes a connection and brings the schema
# from version N-1 to version N. They are applied in order and never edited
# once shipped -- if a migration is wrong, you add a new one that corrects it.
# Editing an applied migration means two databases claiming the same version
# have different shapes.
# --------------------------------------------------------------------------


def _migration_1_baseline(conn: sqlite3.Connection) -> None:
    """The schema as it existed before versioning.

    Idempotent on purpose: the live database already has this table, and
    `user_version` on it is still 0 because nothing ever set it. So this runs
    against an existing table and correctly does nothing.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            text TEXT,
            mood_label TEXT,
            mood_score INTEGER,
            reflection TEXT
        )
        """
    )


def _migration_2_users_and_analysis_status(conn: sqlite3.Connection) -> None:
    """Add accounts, and give every entry an explicit analysis state."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # ALTER TABLE ADD COLUMN appends, so the existing column *order* is
    # preserved -- id, timestamp, text, mood_label, mood_score, reflection stay
    # at indices 0-5. That is why index.html's each_entry[2]/[3]/[5] survives
    # this migration. A table rebuild would reorder and silently break it.
    #
    # user_id is nullable and has to be: SQLite cannot add a NOT NULL column
    # without a default, and there is no sensible default user for rows that
    # predate accounts existing.
    for statement in (
        "ALTER TABLE entries ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE entries ADD COLUMN analysis_status TEXT NOT NULL DEFAULT 'pending'",
        "ALTER TABLE entries ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    ):
        conn.execute(statement)

    # The DEFAULT above is a guess about the past. These rows were written before
    # analysis_status existed, and a row that already has a mood_label is not
    # pending -- the analysis clearly landed. Without this backfill the worker
    # would re-analyse every historical entry and bill for the privilege.
    conn.execute(
        """
        UPDATE entries
           SET analysis_status = CASE
                   WHEN mood_label IS NULL THEN 'pending'
                   ELSE 'ok'
               END
        """
    )


MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _migration_1_baseline),
    (2, _migration_2_users_and_analysis_status),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations the database has not seen. Returns the version now.

    Cheap to call per request: reading `user_version` is a pragma read, and the
    loop body does not run once the database is current.
    """
    current: int = conn.execute("PRAGMA user_version").fetchone()[0]

    for version, apply_migration in MIGRATIONS:
        if version > current:
            apply_migration(conn)
            # PRAGMA will not accept a bound parameter, so this is an f-string.
            # Safe because `version` comes from MIGRATIONS above, never from input.
            conn.execute(f"PRAGMA user_version = {version}")
            current = version

    conn.commit()
    return current


def connect_db() -> sqlite3.Connection:
    """Open the database, bring it up to date, and return the connection."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn
