"""
State manager with incremental sync and rebuild capabilities.

This module manages the in-memory state projection from the event store.
It supports efficient incremental updates and full rebuilds.
"""

import threading
from typing import Optional, Dict, List

from backend.event_store import EventStore
from backend.models import OrchestratorState, Agent, ChatMessage
from backend.projections import apply_event, rebuild_state


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

    def __init__(self, event_store: EventStore):
        """
        Initialize state manager.

        Args:
            event_store: EventStore instance to read events from
        """
        self._event_store = event_store
        self._state = OrchestratorState()
        self._last_event_id = 0
        self._lock = threading.RLock()

        # Perform initial rebuild from all existing events
        self._rebuild_state()

    def _rebuild_state(self) -> None:
        """
        Rebuild complete state from all events in store.

        This is called during initialization and can be called manually
        to reset state to match the event log.

        Thread Safety:
            This method is private and should only be called when lock is held
            or during initialization.
        """
        events = self._event_store.get_all()
        self._state = rebuild_state(events)

        # Update last_event_id to latest event
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

            return len(new_events)

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
