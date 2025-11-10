"""
Snapshot manager for optimizing state rebuilding.

This module provides snapshot functionality to avoid rebuilding state
from thousands of events. Snapshots are saved periodically and used
to speed up state recovery.
"""

import sqlite3
import json
import pickle
import threading
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import asdict

from backend.models import OrchestratorState, Agent, ChatMessage


class SnapshotManager:
    """
    Manages state snapshots for fast recovery.

    Snapshots are saved periodically (e.g., every 1000 events) to avoid
    rebuilding state from the entire event log. This significantly speeds
    up recovery time for systems with many events.

    Storage:
        - Snapshots stored in SQLite database
        - State serialized using pickle for performance
        - Each snapshot includes event_id and timestamp

    Thread Safety:
        - Uses threading.Lock for concurrent access
        - Safe for multiple readers and single writer

    Example:
        >>> snapshot_mgr = SnapshotManager(db_path="snapshots.db", interval=1000)
        >>> if snapshot_mgr.should_snapshot(5000):
        ...     snapshot_mgr.save_snapshot(state, 5000)
        >>> state, event_id = snapshot_mgr.load_latest_snapshot()
    """

    def __init__(self, db_path: str = "snapshots.db", snapshot_interval: int = 1000):
        """
        Initialize snapshot manager.

        Args:
            db_path: Path to SQLite database for snapshots (or ":memory:")
            snapshot_interval: How often to snapshot (in number of events)
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self.snapshot_interval = snapshot_interval
        self._lock = threading.Lock()
        self._conn = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_db()

    def _get_connection(self):
        """Get database connection (reuses in-memory connection)."""
        if self._conn:
            return self._conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize database schema for snapshots."""
        conn = self._get_connection()
        should_close = self._conn is None
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL UNIQUE,
                    state_data BLOB NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT
                )
            ''')
            # Index on event_id for fast lookup
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_snapshots_event_id '
                'ON snapshots(event_id DESC)'
            )
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def should_snapshot(self, event_id: int) -> bool:
        """
        Check if a snapshot should be taken at this event_id.

        Args:
            event_id: Current event ID

        Returns:
            True if snapshot should be taken (event_id is multiple of interval)

        Example:
            >>> mgr = SnapshotManager(snapshot_interval=1000)
            >>> mgr.should_snapshot(1000)
            True
            >>> mgr.should_snapshot(1001)
            False
        """
        if event_id == 0:
            return False
        return event_id % self.snapshot_interval == 0

    def save_snapshot(self, state: OrchestratorState, event_id: int) -> None:
        """
        Save a state snapshot at given event_id.

        Args:
            state: OrchestratorState to snapshot
            event_id: Event ID this state corresponds to

        Example:
            >>> mgr.save_snapshot(state, 1000)
        """
        with self._lock:
            conn = self._get_connection()
            should_close = self._conn is None
            try:
                # Serialize state using pickle for performance
                state_blob = pickle.dumps(state)

                # Store metadata as JSON
                metadata = {
                    "orchestrator_id": state.orchestrator_id,
                    "num_agents": len(state.agents),
                    "num_messages": len(state.chat_history),
                }

                import time
                conn.execute(
                    '''
                    INSERT OR REPLACE INTO snapshots (event_id, state_data, timestamp, metadata)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (event_id, state_blob, time.time(), json.dumps(metadata))
                )
                conn.commit()
            finally:
                if should_close:
                    conn.close()

    def load_latest_snapshot(self) -> Optional[Tuple[OrchestratorState, int]]:
        """
        Load the most recent snapshot.

        Returns:
            Tuple of (state, event_id) if snapshot exists, None otherwise

        Example:
            >>> result = mgr.load_latest_snapshot()
            >>> if result:
            ...     state, event_id = result
            ...     print(f"Loaded snapshot at event {event_id}")
        """
        with self._lock:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            should_close = self._conn is None
            try:
                cursor = conn.execute(
                    'SELECT event_id, state_data FROM snapshots ORDER BY event_id DESC LIMIT 1'
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                event_id = row['event_id']
                state_blob = row['state_data']

                # Deserialize state
                state = pickle.loads(state_blob)

                return (state, event_id)
            finally:
                if should_close:
                    conn.close()

    def get_snapshot_count(self) -> int:
        """
        Get total number of snapshots stored.

        Returns:
            Number of snapshots

        Example:
            >>> mgr.get_snapshot_count()
            5
        """
        with self._lock:
            conn = self._get_connection()
            should_close = self._conn is None
            try:
                cursor = conn.execute('SELECT COUNT(*) as count FROM snapshots')
                return cursor.fetchone()[0]
            finally:
                if should_close:
                    conn.close()

    def delete_old_snapshots(self, keep_count: int = 5) -> int:
        """
        Delete old snapshots, keeping only the most recent N.

        Args:
            keep_count: Number of recent snapshots to keep

        Returns:
            Number of snapshots deleted

        Example:
            >>> deleted = mgr.delete_old_snapshots(keep_count=3)
            >>> print(f"Deleted {deleted} old snapshots")
        """
        with self._lock:
            conn = self._get_connection()
            should_close = self._conn is None
            try:
                # Get the event_id threshold
                cursor = conn.execute(
                    'SELECT event_id FROM snapshots ORDER BY event_id DESC LIMIT 1 OFFSET ?',
                    (keep_count - 1,)
                )
                row = cursor.fetchone()

                if row is None:
                    return 0  # Not enough snapshots to delete

                threshold_event_id = row[0]

                # Delete snapshots older than threshold
                cursor = conn.execute(
                    'DELETE FROM snapshots WHERE event_id < ?',
                    (threshold_event_id,)
                )
                deleted_count = cursor.rowcount
                conn.commit()

                return deleted_count
            finally:
                if should_close:
                    conn.close()


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "SnapshotManager",
]
