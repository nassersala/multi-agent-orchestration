"""
SQLite-based event store for event sourcing.

This module provides an append-only event log with thread-safe operations.
"""

import sqlite3
import json
import time
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path


class EventStore:
    """
    Append-only event log with SQLite backend.

    Thread-safe for single writer, multiple readers.
    All events are immutable once written.
    """

    def __init__(self, db_path: str = "events.db"):
        """
        Initialize event store and create schema if needed.

        Args:
            db_path: Path to SQLite database file (or ":memory:" for in-memory)
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self._lock = threading.Lock()
        # Keep persistent connection for in-memory databases
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
        """Initialize database schema and create tables/indexes."""
        conn = self._get_connection()
        should_close = self._conn is None
        try:
            # Create events table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    aggregate_id TEXT,
                    aggregate_type TEXT,
                    data TEXT NOT NULL,
                    metadata TEXT,
                    timestamp REAL NOT NULL,
                    version INTEGER DEFAULT 1
                )
            ''')

            # Create indexes for performance
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_events_aggregate '
                'ON events(aggregate_id, aggregate_type)'
            )
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_events_type '
                'ON events(type)'
            )
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_events_timestamp '
                'ON events(timestamp DESC)'
            )

            conn.commit()
        finally:
            if should_close:
                conn.close()

    def append(
        self,
        event_type: str,
        data: Dict[str, Any],
        aggregate_id: Optional[str] = None,
        aggregate_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Append event to log.

        Args:
            event_type: Type of event (e.g., "AGENT_CREATED")
            data: Event payload as dictionary
            aggregate_id: Optional entity ID this event relates to
            aggregate_type: Optional entity type (e.g., "agent", "orchestrator")
            metadata: Optional metadata (user_id, ip, etc.)

        Returns:
            Event ID (auto-incremented primary key)

        Example:
            >>> store = EventStore(":memory:")
            >>> event_id = store.append(
            ...     "AGENT_CREATED",
            ...     {"name": "alice", "model": "sonnet"},
            ...     aggregate_id="agent_123",
            ...     aggregate_type="agent"
            ... )
        """
        with self._lock:
            conn = self._get_connection()
            should_close = self._conn is None
            try:
                cursor = conn.execute(
                    '''
                    INSERT INTO events (type, aggregate_id, aggregate_type, data, metadata, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        event_type,
                        aggregate_id,
                        aggregate_type,
                        json.dumps(data),
                        json.dumps(metadata) if metadata else None,
                        time.time()
                    )
                )
                event_id = cursor.lastrowid
                conn.commit()
                return event_id
            finally:
                if should_close:
                    conn.close()

    def get_all(self) -> List[Dict[str, Any]]:
        """
        Get all events in order.

        Returns:
            List of event dictionaries with parsed JSON fields

        Example:
            >>> events = store.get_all()
            >>> len(events)
            5
            >>> events[0]['type']
            'AGENT_CREATED'
        """
        with self._lock:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            should_close = self._conn is None
            try:
                cursor = conn.execute('SELECT * FROM events ORDER BY id')
                events = [dict(row) for row in cursor.fetchall()]

                # Parse JSON fields
                for event in events:
                    event['data'] = json.loads(event['data'])
                    if event['metadata']:
                        event['metadata'] = json.loads(event['metadata'])

                return events
            finally:
                if should_close:
                    conn.close()

    def since(self, event_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get events since given ID.

        Used for SSE streaming and incremental state updates.

        Args:
            event_id: Get events with ID greater than this
            limit: Optional maximum number of events to return

        Returns:
            List of events ordered by ID

        Example:
            >>> new_events = store.since(last_id, limit=100)
        """
        with self._lock:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            should_close = self._conn is None
            try:
                query = 'SELECT * FROM events WHERE id > ? ORDER BY id'
                params = [event_id]

                if limit:
                    query += ' LIMIT ?'
                    params.append(limit)

                cursor = conn.execute(query, params)
                events = [dict(row) for row in cursor.fetchall()]

                # Parse JSON fields
                for event in events:
                    event['data'] = json.loads(event['data'])
                    if event['metadata']:
                        event['metadata'] = json.loads(event['metadata'])

                return events
            finally:
                if should_close:
                    conn.close()

    def by_aggregate(self, aggregate_id: str) -> List[Dict[str, Any]]:
        """
        Get all events for specific aggregate (agent or orchestrator).

        Args:
            aggregate_id: The aggregate ID to filter by

        Returns:
            List of events for this aggregate

        Example:
            >>> agent_events = store.by_aggregate("agent_123")
        """
        with self._lock:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            should_close = self._conn is None
            try:
                cursor = conn.execute(
                    'SELECT * FROM events WHERE aggregate_id = ? ORDER BY id',
                    (aggregate_id,)
                )
                events = [dict(row) for row in cursor.fetchall()]

                # Parse JSON fields
                for event in events:
                    event['data'] = json.loads(event['data'])
                    if event['metadata']:
                        event['metadata'] = json.loads(event['metadata'])

                return events
            finally:
                if should_close:
                    conn.close()

    def by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """
        Get all events of specific type.

        Args:
            event_type: The event type to filter by

        Returns:
            List of events of this type

        Example:
            >>> cost_events = store.by_type("COST_INCURRED")
        """
        with self._lock:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            should_close = self._conn is None
            try:
                cursor = conn.execute(
                    'SELECT * FROM events WHERE type = ? ORDER BY id',
                    (event_type,)
                )
                events = [dict(row) for row in cursor.fetchall()]

                # Parse JSON fields
                for event in events:
                    event['data'] = json.loads(event['data'])
                    if event['metadata']:
                        event['metadata'] = json.loads(event['metadata'])

                return events
            finally:
                if should_close:
                    conn.close()
