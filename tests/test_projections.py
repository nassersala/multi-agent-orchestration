"""
Tests for state projection functions.

Verifies that events are correctly applied to state and that
state can be rebuilt from event history.
"""

import pytest
from datetime import datetime

from backend.projections import apply_event, rebuild_state
from backend.models import OrchestratorState, Agent, ChatMessage
from backend.event_types import (
    ORCHESTRATOR_INITIALIZED,
    ORCHESTRATOR_STATUS_CHANGED,
    AGENT_CREATED,
    AGENT_STATUS_CHANGED,
    AGENT_DELETED,
    COST_INCURRED,
    USER_MESSAGE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED,
    CHAT_MESSAGE_ADDED,
)


# ═══════════════════════════════════════════════════════════
# ORCHESTRATOR EVENT TESTS
# ═══════════════════════════════════════════════════════════

def test_apply_orchestrator_initialized():
    """ORCHESTRATOR_INITIALIZED event should set orchestrator ID and session."""
    state = OrchestratorState()
    event = {
        "type": ORCHESTRATOR_INITIALIZED,
        "data": {
            "orchestrator_id": "orch_123",
            "session_id": "session_456"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert new_state.orchestrator_id == "orch_123"
    assert new_state.session_id == "session_456"
    assert new_state.status == 'idle'
    # Original state unchanged
    assert state.orchestrator_id is None


def test_apply_orchestrator_status_changed():
    """ORCHESTRATOR_STATUS_CHANGED event should update orchestrator status."""
    state = OrchestratorState(status='idle')
    event = {
        "type": ORCHESTRATOR_STATUS_CHANGED,
        "data": {
            "old_status": "idle",
            "new_status": "executing"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert new_state.status == 'executing'
    # Original unchanged
    assert state.status == 'idle'


# ═══════════════════════════════════════════════════════════
# AGENT EVENT TESTS
# ═══════════════════════════════════════════════════════════

def test_apply_agent_created():
    """AGENT_CREATED event should add agent to state."""
    state = OrchestratorState()
    event = {
        "type": AGENT_CREATED,
        "data": {
            "name": "alice",
            "model": "sonnet",
            "system_prompt": "You are a helpful agent",
            "session_id": "session_123"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert "alice" in new_state.agents
    assert new_state.agents["alice"].name == "alice"
    assert new_state.agents["alice"].model == "sonnet"
    assert new_state.agents["alice"].system_prompt == "You are a helpful agent"
    assert new_state.agents["alice"].session_id == "session_123"
    assert new_state.agents["alice"].status == 'idle'
    # Original state unchanged
    assert "alice" not in state.agents


def test_apply_agent_status_changed():
    """AGENT_STATUS_CHANGED event should update agent status."""
    agent = Agent(name="alice", model="sonnet", status='idle')
    state = OrchestratorState(agents={"alice": agent})

    event = {
        "type": AGENT_STATUS_CHANGED,
        "data": {
            "agent_name": "alice",
            "old_status": "idle",
            "new_status": "executing"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert new_state.agents["alice"].status == 'executing'
    # Original unchanged
    assert state.agents["alice"].status == 'idle'


def test_apply_agent_status_changed_nonexistent_agent():
    """AGENT_STATUS_CHANGED for nonexistent agent should return state unchanged."""
    state = OrchestratorState()
    event = {
        "type": AGENT_STATUS_CHANGED,
        "data": {
            "agent_name": "bob",
            "new_status": "executing"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    # State unchanged
    assert new_state == state


def test_apply_agent_deleted():
    """AGENT_DELETED event should remove agent from state."""
    agent = Agent(name="alice", model="sonnet")
    state = OrchestratorState(agents={"alice": agent})

    event = {
        "type": AGENT_DELETED,
        "data": {
            "agent_name": "alice"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert "alice" not in new_state.agents
    # Original unchanged
    assert "alice" in state.agents


def test_apply_agent_deleted_nonexistent_agent():
    """AGENT_DELETED for nonexistent agent should return state unchanged."""
    state = OrchestratorState()
    event = {
        "type": AGENT_DELETED,
        "data": {
            "agent_name": "bob"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    # State unchanged
    assert new_state == state


# ═══════════════════════════════════════════════════════════
# COST EVENT TESTS
# ═══════════════════════════════════════════════════════════

def test_apply_cost_incurred_orchestrator_only():
    """COST_INCURRED without agent_name should update orchestrator totals only."""
    state = OrchestratorState()
    event = {
        "type": COST_INCURRED,
        "data": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": 0.05
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert new_state.total_input_tokens == 100
    assert new_state.total_output_tokens == 50
    assert new_state.total_cost == pytest.approx(0.05)
    # Original unchanged
    assert state.total_input_tokens == 0


def test_apply_cost_incurred_with_agent():
    """COST_INCURRED with agent_name should update both orchestrator and agent."""
    agent = Agent(name="alice", model="sonnet")
    state = OrchestratorState(agents={"alice": agent})

    event = {
        "type": COST_INCURRED,
        "data": {
            "agent_name": "alice",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": 0.05
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    # Orchestrator totals updated
    assert new_state.total_input_tokens == 100
    assert new_state.total_output_tokens == 50
    assert new_state.total_cost == pytest.approx(0.05)

    # Agent totals updated
    assert new_state.agents["alice"].input_tokens == 100
    assert new_state.agents["alice"].output_tokens == 50
    assert new_state.agents["alice"].total_cost == pytest.approx(0.05)

    # Original unchanged
    assert state.agents["alice"].input_tokens == 0


def test_apply_cost_incurred_accumulates():
    """Multiple COST_INCURRED events should accumulate."""
    state = OrchestratorState()

    event1 = {
        "type": COST_INCURRED,
        "data": {"input_tokens": 100, "output_tokens": 50, "cost": 0.05},
        "timestamp": datetime.utcnow().timestamp()
    }
    event2 = {
        "type": COST_INCURRED,
        "data": {"input_tokens": 200, "output_tokens": 100, "cost": 0.10},
        "timestamp": datetime.utcnow().timestamp()
    }

    state = apply_event(state, event1)
    state = apply_event(state, event2)

    assert state.total_input_tokens == 300
    assert state.total_output_tokens == 150
    assert state.total_cost == pytest.approx(0.15)


# ═══════════════════════════════════════════════════════════
# CHAT MESSAGE EVENT TESTS
# ═══════════════════════════════════════════════════════════

def test_apply_user_message_received():
    """USER_MESSAGE_RECEIVED event should add message to chat history."""
    state = OrchestratorState()
    event = {
        "type": USER_MESSAGE_RECEIVED,
        "data": {
            "message": "Hello orchestrator!"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert len(new_state.chat_history) == 1
    assert new_state.chat_history[0].sender == 'user'
    assert new_state.chat_history[0].receiver == 'orchestrator'
    assert new_state.chat_history[0].message == "Hello orchestrator!"
    # Original unchanged
    assert len(state.chat_history) == 0


def test_apply_orchestrator_response_generated():
    """ORCHESTRATOR_RESPONSE_GENERATED event should add message to chat history."""
    state = OrchestratorState()
    event = {
        "type": ORCHESTRATOR_RESPONSE_GENERATED,
        "data": {
            "message": "Hello user!"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert len(new_state.chat_history) == 1
    assert new_state.chat_history[0].sender == 'orchestrator'
    assert new_state.chat_history[0].receiver == 'user'
    assert new_state.chat_history[0].message == "Hello user!"


def test_apply_chat_message_added():
    """CHAT_MESSAGE_ADDED event should add generic message to chat history."""
    state = OrchestratorState()
    event = {
        "type": CHAT_MESSAGE_ADDED,
        "data": {
            "sender": "agent",
            "receiver": "orchestrator",
            "message": "Task complete",
            "agent_name": "alice"
        },
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    assert len(new_state.chat_history) == 1
    assert new_state.chat_history[0].sender == 'agent'
    assert new_state.chat_history[0].receiver == 'orchestrator'
    assert new_state.chat_history[0].message == "Task complete"
    assert new_state.chat_history[0].agent_name == "alice"


def test_chat_messages_ordered():
    """Multiple chat messages should maintain order."""
    state = OrchestratorState()

    event1 = {
        "type": USER_MESSAGE_RECEIVED,
        "data": {"message": "First"},
        "timestamp": datetime.utcnow().timestamp()
    }
    event2 = {
        "type": ORCHESTRATOR_RESPONSE_GENERATED,
        "data": {"message": "Second"},
        "timestamp": datetime.utcnow().timestamp()
    }

    state = apply_event(state, event1)
    state = apply_event(state, event2)

    assert len(state.chat_history) == 2
    assert state.chat_history[0].message == "First"
    assert state.chat_history[1].message == "Second"


# ═══════════════════════════════════════════════════════════
# UNKNOWN EVENT & IMMUTABILITY TESTS
# ═══════════════════════════════════════════════════════════

def test_apply_unknown_event_type():
    """Unknown event types should return state unchanged."""
    state = OrchestratorState(orchestrator_id="orch_123")
    event = {
        "type": "UNKNOWN_EVENT_TYPE",
        "data": {"foo": "bar"},
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    # State completely unchanged
    assert new_state == state
    assert new_state.orchestrator_id == "orch_123"


def test_apply_event_preserves_immutability():
    """apply_event should never mutate the original state."""
    agent = Agent(name="alice", model="sonnet", status='idle')
    state = OrchestratorState(
        orchestrator_id="orch_123",
        agents={"alice": agent},
        total_cost=0.0
    )

    event = {
        "type": COST_INCURRED,
        "data": {"agent_name": "alice", "input_tokens": 100, "output_tokens": 50, "cost": 0.05},
        "timestamp": datetime.utcnow().timestamp()
    }

    new_state = apply_event(state, event)

    # Original state completely unchanged
    assert state.total_cost == 0.0
    assert state.agents["alice"].total_cost == 0.0
    assert state.agents["alice"].input_tokens == 0

    # New state has changes
    assert new_state.total_cost == pytest.approx(0.05)
    assert new_state.agents["alice"].total_cost == pytest.approx(0.05)
    assert new_state.agents["alice"].input_tokens == 100


# ═══════════════════════════════════════════════════════════
# REBUILD STATE TESTS
# ═══════════════════════════════════════════════════════════

def test_rebuild_state_from_empty_list():
    """rebuild_state with empty list should return default state."""
    state = rebuild_state([])

    assert state.orchestrator_id is None
    assert state.agents == {}
    assert state.chat_history == []
    assert state.total_cost == 0.0


def test_rebuild_state_from_single_event():
    """rebuild_state with single event should apply it."""
    events = [
        {
            "type": ORCHESTRATOR_INITIALIZED,
            "data": {"orchestrator_id": "orch_123", "session_id": "session_456"},
            "timestamp": datetime.utcnow().timestamp()
        }
    ]

    state = rebuild_state(events)

    assert state.orchestrator_id == "orch_123"
    assert state.session_id == "session_456"


def test_rebuild_state_from_sequence():
    """rebuild_state should apply all events in order."""
    events = [
        {
            "type": ORCHESTRATOR_INITIALIZED,
            "data": {"orchestrator_id": "orch_123"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_CREATED,
            "data": {"name": "alice", "model": "sonnet"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_CREATED,
            "data": {"name": "bob", "model": "haiku"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": USER_MESSAGE_RECEIVED,
            "data": {"message": "Hello"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": COST_INCURRED,
            "data": {"agent_name": "alice", "input_tokens": 100, "output_tokens": 50, "cost": 0.05},
            "timestamp": datetime.utcnow().timestamp()
        },
    ]

    state = rebuild_state(events)

    # All events applied
    assert state.orchestrator_id == "orch_123"
    assert len(state.agents) == 2
    assert "alice" in state.agents
    assert "bob" in state.agents
    assert len(state.chat_history) == 1
    assert state.total_cost == pytest.approx(0.05)
    assert state.agents["alice"].total_cost == pytest.approx(0.05)


def test_rebuild_state_with_agent_lifecycle():
    """rebuild_state should handle complete agent lifecycle."""
    events = [
        {
            "type": AGENT_CREATED,
            "data": {"name": "alice", "model": "sonnet"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_STATUS_CHANGED,
            "data": {"agent_name": "alice", "new_status": "executing"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": COST_INCURRED,
            "data": {"agent_name": "alice", "input_tokens": 100, "output_tokens": 50, "cost": 0.05},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_STATUS_CHANGED,
            "data": {"agent_name": "alice", "new_status": "complete"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_DELETED,
            "data": {"agent_name": "alice"},
            "timestamp": datetime.utcnow().timestamp()
        },
    ]

    state = rebuild_state(events)

    # Agent created, used, then deleted
    assert "alice" not in state.agents
    # But costs still accumulated
    assert state.total_cost == pytest.approx(0.05)


def test_rebuild_state_ignores_unknown_events():
    """rebuild_state should gracefully handle unknown event types."""
    events = [
        {
            "type": ORCHESTRATOR_INITIALIZED,
            "data": {"orchestrator_id": "orch_123"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": "UNKNOWN_EVENT",
            "data": {"foo": "bar"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_CREATED,
            "data": {"name": "alice", "model": "sonnet"},
            "timestamp": datetime.utcnow().timestamp()
        },
    ]

    state = rebuild_state(events)

    # Known events applied, unknown ignored
    assert state.orchestrator_id == "orch_123"
    assert "alice" in state.agents


def test_rebuild_state_complex_conversation():
    """rebuild_state should handle complex conversation flow."""
    events = [
        {
            "type": ORCHESTRATOR_INITIALIZED,
            "data": {"orchestrator_id": "orch_123"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": USER_MESSAGE_RECEIVED,
            "data": {"message": "Create an agent"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": ORCHESTRATOR_RESPONSE_GENERATED,
            "data": {"message": "Creating agent alice"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": AGENT_CREATED,
            "data": {"name": "alice", "model": "sonnet"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": USER_MESSAGE_RECEIVED,
            "data": {"message": "What's the status?"},
            "timestamp": datetime.utcnow().timestamp()
        },
        {
            "type": ORCHESTRATOR_RESPONSE_GENERATED,
            "data": {"message": "Agent alice is idle"},
            "timestamp": datetime.utcnow().timestamp()
        },
    ]

    state = rebuild_state(events)

    assert state.orchestrator_id == "orch_123"
    assert len(state.agents) == 1
    assert len(state.chat_history) == 4  # 2 user + 2 orchestrator messages
    assert state.chat_history[0].sender == 'user'
    assert state.chat_history[1].sender == 'orchestrator'
    assert state.chat_history[2].sender == 'user'
    assert state.chat_history[3].sender == 'orchestrator'
