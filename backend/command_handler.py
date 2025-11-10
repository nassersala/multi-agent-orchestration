"""
Command handler for processing user commands.

The CommandHandler is responsible for:
1. Validating commands against current state
2. Generating appropriate events
3. Persisting events to the event store
4. Producing side effects to be executed

All methods are pure functions that return (event_ids, effects) tuples.
"""

import time
from typing import List, Tuple, Optional
from datetime import datetime

from backend.event_store import EventStore
from backend.state_manager import StateManager
from backend.effects import Effect
from backend.event_types import (
    AGENT_CREATED,
    AGENT_COMMANDED,
    USER_MESSAGE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED,
)
from backend.models import Agent


class CommandHandler:
    """
    Pure command handler that validates commands and generates events.

    The CommandHandler maintains pure function semantics by:
    - Only reading from StateManager (via get_state())
    - Only writing to EventStore (append-only)
    - Returning effects for execution by EffectExecutor
    - Not performing any side effects directly

    Example:
        >>> store = EventStore(":memory:")
        >>> state_mgr = StateManager(store)
        >>> handler = CommandHandler(store, state_mgr)
        >>> event_ids, effects = handler.handle_create_agent("alice", "You are Alice", "claude-3-5-sonnet-20241022")
        >>> # Events are persisted, effects need to be executed separately
    """

    def __init__(self, event_store: EventStore, state_manager: StateManager):
        """
        Initialize command handler.

        Args:
            event_store: EventStore to persist events to
            state_manager: StateManager to read current state from
        """
        self._event_store = event_store
        self._state_manager = state_manager

    def handle_create_agent(
        self,
        name: str,
        system_prompt: str,
        model: str = "claude-3-5-sonnet-20241022",
        template: Optional[str] = None
    ) -> Tuple[List[int], List[Effect]]:
        """
        Handle create agent command.

        Validates that no agent with this name exists, then creates events
        and effects for agent creation.

        Args:
            name: Unique agent name
            system_prompt: System prompt for the agent
            model: Claude model to use (default: claude-3-5-sonnet-20241022)
            template: Optional template name for agent configuration

        Returns:
            Tuple of (event_ids, effects)
                - event_ids: List of event IDs that were created
                - effects: List of Effect objects to be executed

        Raises:
            ValueError: If agent with this name already exists
        """
        # Validate: agent name must be unique
        state = self._state_manager.get_state()
        if name in state.agents:
            raise ValueError(f"Agent '{name}' already exists")

        # Generate event
        event_data = {
            "name": name,
            "model": model,
            "system_prompt": system_prompt,
            "status": "idle",
            "created_at": datetime.utcnow().isoformat(),
        }
        if template:
            event_data["template"] = template

        event_id = self._event_store.append(
            event_type=AGENT_CREATED,
            data=event_data,
            aggregate_id=name,
            aggregate_type="agent"
        )

        # Sync state manager to include new event
        self._state_manager.sync()

        # Generate effect to create Claude client
        effect = Effect(
            type="create_claude_client",
            data={
                "agent_name": name,
                "model": model,
                "system_prompt": system_prompt,
                "template": template,
            }
        )

        return [event_id], [effect]

    def handle_command_agent(
        self,
        agent_name: str,
        command: str
    ) -> Tuple[List[int], List[Effect]]:
        """
        Handle command agent command.

        Validates that the agent exists, then creates events and effects
        for executing the command.

        Args:
            agent_name: Name of agent to command
            command: Command/prompt to send to agent

        Returns:
            Tuple of (event_ids, effects)

        Raises:
            ValueError: If agent does not exist
        """
        # Validate: agent must exist
        state = self._state_manager.get_state()
        if agent_name not in state.agents:
            raise ValueError(f"Agent '{agent_name}' does not exist")

        # Generate event
        event_data = {
            "agent_name": agent_name,
            "command": command,
            "timestamp": datetime.utcnow().isoformat(),
        }

        event_id = self._event_store.append(
            event_type=AGENT_COMMANDED,
            data=event_data,
            aggregate_id=agent_name,
            aggregate_type="agent"
        )

        # Sync state manager
        self._state_manager.sync()

        # Generate effect to execute agent command
        effect = Effect(
            type="execute_agent_command",
            data={
                "agent_name": agent_name,
                "command": command,
            }
        )

        return [event_id], [effect]

    def handle_user_message(
        self,
        message: str
    ) -> Tuple[List[int], List[Effect]]:
        """
        Handle user message command.

        Records user message and generates orchestrator response effect.

        Args:
            message: User's message to the orchestrator

        Returns:
            Tuple of (event_ids, effects)
        """
        event_ids = []

        # Generate user message event
        user_event_data = {
            "sender": "user",
            "receiver": "orchestrator",
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        user_event_id = self._event_store.append(
            event_type=USER_MESSAGE_RECEIVED,
            data=user_event_data,
            aggregate_type="chat"
        )
        event_ids.append(user_event_id)

        # Sync state manager
        self._state_manager.sync()

        # Generate effect to execute orchestrator
        effect = Effect(
            type="execute_orchestrator",
            data={
                "message": message,
            }
        )

        return event_ids, [effect]


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "CommandHandler",
]
