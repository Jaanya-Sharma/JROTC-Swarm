"""SQLite setup for persisted radar track samples."""

from __future__ import annotations

import sqlite3
import time
from collections import deque
from pathlib import Path


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "radar.db"


def open_database(path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open the radar database, enable WAL, and ensure its schema exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS track_samples (
            ts_ms INTEGER NOT NULL,
            track_id INTEGER NOT NULL,
            bearing REAL NOT NULL,
            range_u REAL NOT NULL,
            heading REAL NOT NULL,
            rel_speed_u REAL NOT NULL,
            altitude_m REAL,
            confidence REAL NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_samples_ts_ms ON track_samples (ts_ms)"
    )
    connection.commit()
    return connection


class TrackSampleWriter:
    """Buffer track samples and persist them in batched SQLite transactions."""

    FLUSH_INTERVAL_SECONDS = 0.2
    FLUSH_ROW_COUNT = 500
    MAX_BUFFER_ROWS = 5_000

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._buffer: deque[tuple] = deque(maxlen=self.MAX_BUFFER_ROWS)
        self._last_flush_at = time.monotonic()

    def add_sample(self, sample: dict) -> None:
        """Queue a sample and flush when its time or row threshold is reached."""
        self._buffer.append(
            (
                sample["ts_ms"],
                sample["track_id"],
                sample["bearing"],
                sample["range_u"],
                sample["heading"],
                sample["rel_speed_u"],
                sample.get("altitude_m"),
                sample["confidence"],
            )
        )
        if (
            len(self._buffer) >= self.FLUSH_ROW_COUNT
            or time.monotonic() - self._last_flush_at >= self.FLUSH_INTERVAL_SECONDS
        ):
            self.flush()

    def flush(self) -> None:
        """Write all currently buffered rows in one transaction."""
        if not self._buffer:
            return

        rows = list(self._buffer)
        self._buffer.clear()
        try:
            with self.connection:
                self.connection.executemany(
                    """
                    INSERT INTO track_samples (
                        ts_ms, track_id, bearing, range_u, heading,
                        rel_speed_u, altitude_m, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        except Exception:
            self._buffer.extendleft(reversed(rows))
            raise
        else:
            self._last_flush_at = time.monotonic()
