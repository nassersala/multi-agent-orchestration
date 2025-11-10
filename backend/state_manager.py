"""
State manager with incremental sync and rebuild capabilities.

This module manages the in-memory state projection from the event store.
It supports efficient incremental updates and full rebuilds.
"""

import threading
from typing import Optional, Dict, List, TYPE_CHECKING

from backend.event_store import EventStore
from backend.models import OrchestratorState, Agent, ChatMessage
from backend.projections import apply_event, rebuild_state

if TYPE_CHECKING:
    from backend.snapshot_manager import SnapshotManager


class StateManager:
    """
    Manages in-memory state synchronized with event store.

    The StateManager maintains a current state projection and incrementally
    applies new events. It supports thread-safe access from multiple readers
    and handles rebuilding state from the complete event log.

    Thread Safety:
        - Uses RLock for reentrant locking (safe for recursive calls)
        - All public methods acquire the lock
        - Multiple readers can access state safely
        - Single writer (the sync process)

    Example:
        >>> store = EventStore(":memory:")
        >>> manager = StateManager(store)
        >>> manager.get_state()
        OrchestratorState(...)
        >>> manager.sync()  # Apply new events
        >>> manager.get_agents()
        {'alice': Agent(...)}
    """

    def __init__(
        self,
        event_store: EventStore,
        snapshot_manager: Optional['SnapshotManager'] = None
    ):
        """
        Initialize state manager.

        Args:
            event_store: EventStore instance to read events from
            snapshot_manager: Optional SnapshotManager for fast recovery
        """
        self._event_store = event_store
        self._snapshot_manager = snapshot_manager
        self._state = OrchestratorState()
        self._last_event_id = 0
        self._lock = threading.RLock()

        # Perform initial rebuild from all existing events (or snapshot)
        self._rebuild_state()

    def _rebuild_state(self) -> None:
        """
        Rebuild complete state from all events in store.

        If snapshot_manager is configured, this will load the latest snapshot
        and only replay events since that snapshot, significantly improving
        performance for large event logs.

        This is called during initialization and can be called manually
        to reset state to match the event log.

        Thread Safety:
            This method is private and should only be called when lock is held
            or during initialization.
        """
        # Try to load from snapshot first
        if self._snapshot_manager:
            snapshot_result = self._snapshot_manager.load_latest_snapshot()
            if snapshot_result:
                self._state, self._last_event_id = snapshot_result
                # Only replay events since snapshot
                events = self._event_store.since(self._last_event_id)
                for event in events:
                    self._state = apply_event(self._state, event)
                    self._last_event_id = event['id']
                    self.maybe_snapshot()
                return

        # No snapshot available - rebuild from all events
        events = self._event_store.get_all()

        # If we have snapshot manager, apply events one by one to create snapshots
        if self._snapshot_manager and events:
            self._state = OrchestratorState()
            for event in events:
                self._state = apply_event(self._state, event)
                self._last_event_id = event['id']
                self.maybe_snapshot()
        else:
            # No snapshot manager - use fast rebuild
            self._state = rebuild_state(events)
            if events:
                self._last_event_id = events[-1]['id']
            else:
                self._last_event_id = 0

    def sync(self) -> int:
        """
        Synchronize state with new events from store.

        Applies all events that occurred since last sync.
        This is more efficient than rebuilding for incremental updates.

        Returns:
            Number of new events applied

        Example:
            >>> manager.sync()
            3  # Applied 3 new events
        """
        with self._lock:
            new_events = self._event_store.since(self._last_event_id)

            for event in new_events:
                self._state = apply_event(self._state, event)
                self._last_event_id = event['id']

                # Optionally create snapshot after applying event
                self.maybe_snapshot()

            return len(new_events)

    def maybe_snapshot(self) -> bool:
        """
        Check if snapshot should be taken and save it if needed.

        This is automatically called during sync() if snapshot_manager is configured.
        It can also be called manually to force snapshot evaluation.

        Returns:
            True if snapshot was taken, False otherwise

        Example:
            >>> manager.sync()
            >>> manager.maybe_snapshot()  # Usually called automatically
            True
        """
        if not self._snapshot_manager:
            return False

        if self._snapshot_manager.should_snapshot(self._last_event_id):
            self._snapshot_manager.save_snapshot(self._state, self._last_event_id)
            return True

        return False

    def get_state(self) -> OrchestratorState:
        """
        Get current complete state.

        Returns:
            Immutable OrchestratorState instance

        Thread Safety:
            Returns a frozen dataclass, safe to use outside lock
        """
        with self._lock:
            return self._state

    def get_agents(self) -> Dict[str, Agent]:
        """
        Get all agents.

        Returns:
            Dictionary mapping agent name to Agent instance

        Example:
            >>> agents = manager.get_agents()
            >>> agents['alice'].status
            'idle'
        """
        with self._lock:
            return self._state.agents

    def get_agent(self, name: str) -> Optional[Agent]:
        """
        Get specific agent by name.

        Args:
            name: Agent name

        Returns:
            Agent instance or None if not found

        Example:
            >>> agent = manager.get_agent('alice')
            >>> if agent:
            ...     print(agent.model)
        """
        with self._lock:
            return self._state.agents.get(name)

    def get_chat_history(self, limit: Optional[int] = None) -> List[ChatMessage]:
        """
        Get chat history, optionally limited to recent messages.

        Args:
            limit: Maximum number of recent messages to return (None = all)

        Returns:
            List of ChatMessage instances (most recent first if limited)

        Example:
            >>> recent = manager.get_chat_history(limit=10)
            >>> len(recent)
            10
        """
        with self._lock:
            history = self._state.chat_history

            if limit is not None and limit > 0:
                # Return last N messages
                return history[-limit:]

            return history


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "StateManager",
]
