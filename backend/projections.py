"""
Pure functions for projecting events onto state.

These functions are the heart of event sourcing - they take an immutable state
and an event, and return a new immutable state. No side effects, no mutations.
"""

from typing import Dict, Any, List
from datetime import datetime

from backend.models import OrchestratorState, Agent, ChatMessage
from backend.event_types import (
    ORCHESTRATOR_INITIALIZED,
    AGENT_CREATED,
    AGENT_STATUS_CHANGED,
    AGENT_DELETED,
    COST_INCURRED,
    USER_MESSAGE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED,
    CHAT_MESSAGE_ADDED,
    ORCHESTRATOR_STATUS_CHANGED,
)


def apply_event(state: OrchestratorState, event: Dict[str, Any]) -> OrchestratorState:
    """
    Apply a single event to state and return new state.

    This is a pure function - it never mutates the input state.
    Unknown event types are ignored (state returned unchanged).

    Args:
        state: Current immutable state
        event: Event dictionary with 'type' and 'data' fields

    Returns:
        New immutable state with event applied

    Example:
        >>> state = OrchestratorState()
        >>> event = {"type": "AGENT_CREATED", "data": {"name": "alice", "model": "sonnet"}}
        >>> new_state = apply_event(state, event)
        >>> "alice" in new_state.agents
        True
    """
    event_type = event.get("type")
    data = event.get("data", {})
    timestamp = datetime.fromtimestamp(event.get("timestamp", datetime.utcnow().timestamp()))

    # Route to appropriate handler based on event type
    if event_type == ORCHESTRATOR_INITIALIZED:
        return _apply_orchestrator_initialized(state, data)

    elif event_type == ORCHESTRATOR_STATUS_CHANGED:
        return _apply_orchestrator_status_changed(state, data)

    elif event_type == AGENT_CREATED:
        return _apply_agent_created(state, data, timestamp)

    elif event_type == AGENT_STATUS_CHANGED:
        return _apply_agent_status_changed(state, data)

    elif event_type == AGENT_DELETED:
        return _apply_agent_deleted(state, data)

    elif event_type == COST_INCURRED:
        return _apply_cost_incurred(state, data)

    elif event_type == USER_MESSAGE_RECEIVED:
        return _apply_user_message_received(state, data, timestamp)

    elif event_type == ORCHESTRATOR_RESPONSE_GENERATED:
        return _apply_orchestrator_response_generated(state, data, timestamp)

    elif event_type == CHAT_MESSAGE_ADDED:
        return _apply_chat_message_added(state, data, timestamp)

    else:
        # Unknown event type - return state unchanged
        return state


def rebuild_state(events: List[Dict[str, Any]]) -> OrchestratorState:
    """
    Rebuild complete state from event history.

    This is the magic of event sourcing - we can reconstruct the entire
    state of the system by replaying all events in order.

    Args:
        events: List of event dictionaries in chronological order

    Returns:
        Final state after applying all events

    Example:
        >>> events = [
        ...     {"type": "ORCHESTRATOR_INITIALIZED", "data": {"id": "orch_1"}},
        ...     {"type": "AGENT_CREATED", "data": {"name": "alice", "model": "sonnet"}}
        ... ]
        >>> state = rebuild_state(events)
        >>> state.orchestrator_id
        'orch_1'
        >>> "alice" in state.agents
        True
    """
    state = OrchestratorState()
    for event in events:
        state = apply_event(state, event)
    return state


# ═══════════════════════════════════════════════════════════
# EVENT HANDLERS (PRIVATE)
# ═══════════════════════════════════════════════════════════

def _apply_orchestrator_initialized(state: OrchestratorState, data: Dict[str, Any]) -> OrchestratorState:
    """Handle ORCHESTRATOR_INITIALIZED event."""
    from dataclasses import replace
    return replace(
        state,
        orchestrator_id=data.get("orchestrator_id"),
        session_id=data.get("session_id"),
        status='idle',
        last_updated=datetime.utcnow()
    )


def _apply_orchestrator_status_changed(state: OrchestratorState, data: Dict[str, Any]) -> OrchestratorState:
    """Handle ORCHESTRATOR_STATUS_CHANGED event."""
    new_status = data.get("new_status")
    if new_status:
        return state.with_status(new_status)
    return state


def _apply_agent_created(state: OrchestratorState, data: Dict[str, Any], timestamp: datetime) -> OrchestratorState:
    """Handle AGENT_CREATED event."""
    agent = Agent(
        name=data.get("name"),
        model=data.get("model", "sonnet"),
        system_prompt=data.get("system_prompt", ""),
        status='idle',
        session_id=data.get("session_id"),
        working_dir=data.get("working_dir"),
        created_at=timestamp
    )
    return state.with_agent(agent)


def _apply_agent_status_changed(state: OrchestratorState, data: Dict[str, Any]) -> OrchestratorState:
    """Handle AGENT_STATUS_CHANGED event."""
    agent_name = data.get("agent_name")
    new_status = data.get("new_status")

    if not agent_name or agent_name not in state.agents:
        return state

    agent = state.agents[agent_name]
    updated_agent = agent.with_status(new_status)
    return state.with_agent(updated_agent)


def _apply_agent_deleted(state: OrchestratorState, data: Dict[str, Any]) -> OrchestratorState:
    """Handle AGENT_DELETED event."""
    agent_name = data.get("agent_name")
    if agent_name and agent_name in state.agents:
        return state.without_agent(agent_name)
    return state


def _apply_cost_incurred(state: OrchestratorState, data: Dict[str, Any]) -> OrchestratorState:
    """Handle COST_INCURRED event."""
    agent_name = data.get("agent_name")
    input_tokens = data.get("input_tokens", 0)
    output_tokens = data.get("output_tokens", 0)
    cost = data.get("cost", 0.0)

    # Update orchestrator totals
    new_state = state.with_cost(input_tokens, output_tokens, cost)

    # Update agent-specific totals if agent specified
    if agent_name and agent_name in new_state.agents:
        agent = new_state.agents[agent_name]
        updated_agent = agent.with_cost(input_tokens, output_tokens, cost)
        new_state = new_state.with_agent(updated_agent)

    return new_state


def _apply_user_message_received(state: OrchestratorState, data: Dict[str, Any], timestamp: datetime) -> OrchestratorState:
    """Handle USER_MESSAGE_RECEIVED event."""
    message = ChatMessage(
        sender='user',
        receiver='orchestrator',
        message=data.get("message", ""),
        timestamp=timestamp,
        metadata=data.get("metadata", {})
    )
    return state.with_message(message)


def _apply_orchestrator_response_generated(state: OrchestratorState, data: Dict[str, Any], timestamp: datetime) -> OrchestratorState:
    """Handle ORCHESTRATOR_RESPONSE_GENERATED event."""
    message = ChatMessage(
        sender='orchestrator',
        receiver='user',
        message=data.get("message", ""),
        timestamp=timestamp,
        metadata=data.get("metadata", {})
    )
    return state.with_message(message)


def _apply_chat_message_added(state: OrchestratorState, data: Dict[str, Any], timestamp: datetime) -> OrchestratorState:
    """Handle CHAT_MESSAGE_ADDED event (generic chat message)."""
    message = ChatMessage(
        sender=data.get("sender", 'user'),
        receiver=data.get("receiver", 'orchestrator'),
        message=data.get("message", ""),
        timestamp=timestamp,
        agent_name=data.get("agent_name"),
        metadata=data.get("metadata", {})
    )
    return state.with_message(message)


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "apply_event",
    "rebuild_state",
]
