"""
Tests for command handler.

Tests command validation, event generation, and effect production.
All tests use real EventStore and StateManager (no mocks).
"""

import pytest
from datetime import datetime

from backend.event_store import EventStore
from backend.state_manager import StateManager
from backend.command_handler import CommandHandler
from backend.effects import Effect
from backend.event_types import (
    AGENT_CREATED,
    AGENT_COMMANDED,
    USER_MESSAGE_RECEIVED,
)


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def event_store():
    """Create in-memory event store for testing."""
    return EventStore(":memory:")


@pytest.fixture
def state_manager(event_store):
    """Create state manager with in-memory store."""
    return StateManager(event_store)


@pytest.fixture
def command_handler(event_store, state_manager):
    """Create command handler with in-memory store."""
    return CommandHandler(event_store, state_manager)


# ═══════════════════════════════════════════════════════════
# CREATE AGENT TESTS
# ═══════════════════════════════════════════════════════════

def test_handle_create_agent_success(command_handler, event_store, state_manager):
    """Test successful agent creation."""
    # Execute command
    event_ids, effects = command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice, a helpful assistant",
        model="claude-3-5-sonnet-20241022"
    )

    # Verify event IDs returned
    assert len(event_ids) == 1
    assert isinstance(event_ids[0], int)
    assert event_ids[0] > 0

    # Verify effects returned
    assert len(effects) == 1
    assert isinstance(effects[0], Effect)
    assert effects[0].type == "create_claude_client"
    assert effects[0].data["agent_name"] == "alice"
    assert effects[0].data["model"] == "claude-3-5-sonnet-20241022"
    assert effects[0].data["system_prompt"] == "You are Alice, a helpful assistant"

    # Verify event persisted in store
    events = event_store.get_all()
    assert len(events) == 1
    assert events[0]["type"] == AGENT_CREATED
    assert events[0]["data"]["name"] == "alice"
    assert events[0]["data"]["model"] == "claude-3-5-sonnet-20241022"
    assert events[0]["data"]["system_prompt"] == "You are Alice, a helpful assistant"
    assert events[0]["data"]["status"] == "idle"
    assert events[0]["aggregate_id"] == "alice"
    assert events[0]["aggregate_type"] == "agent"

    # Verify state updated
    state = state_manager.get_state()
    assert "alice" in state.agents
    agent = state.agents["alice"]
    assert agent.name == "alice"
    assert agent.model == "claude-3-5-sonnet-20241022"
    assert agent.system_prompt == "You are Alice, a helpful assistant"
    assert agent.status == "idle"


def test_handle_create_agent_with_template(command_handler, event_store):
    """Test agent creation with template."""
    event_ids, effects = command_handler.handle_create_agent(
        name="bob",
        system_prompt="You are Bob",
        model="claude-3-5-sonnet-20241022",
        template="code_reviewer"
    )

    # Verify template in event and effect
    events = event_store.get_all()
    assert events[0]["data"]["template"] == "code_reviewer"
    assert effects[0].data["template"] == "code_reviewer"


def test_handle_create_agent_duplicate_name_error(command_handler):
    """Test that creating duplicate agent raises error."""
    # Create first agent
    command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )

    # Attempt to create duplicate
    with pytest.raises(ValueError, match="Agent 'alice' already exists"):
        command_handler.handle_create_agent(
            name="alice",
            system_prompt="You are also Alice",
            model="claude-3-5-sonnet-20241022"
        )


def test_handle_create_agent_timestamp_populated(command_handler, event_store):
    """Test that created_at timestamp is populated."""
    before = datetime.utcnow()
    command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )
    after = datetime.utcnow()

    events = event_store.get_all()
    created_at = datetime.fromisoformat(events[0]["data"]["created_at"])
    assert before <= created_at <= after


# ═══════════════════════════════════════════════════════════
# COMMAND AGENT TESTS
# ═══════════════════════════════════════════════════════════

def test_handle_command_agent_success(command_handler, event_store, state_manager):
    """Test successful agent command."""
    # Create agent first
    command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )

    # Command agent
    event_ids, effects = command_handler.handle_command_agent(
        agent_name="alice",
        command="Write a Python function to calculate fibonacci numbers"
    )

    # Verify event IDs returned
    assert len(event_ids) == 1
    assert isinstance(event_ids[0], int)
    assert event_ids[0] > 0

    # Verify effects returned
    assert len(effects) == 1
    assert isinstance(effects[0], Effect)
    assert effects[0].type == "execute_agent_command"
    assert effects[0].data["agent_name"] == "alice"
    assert effects[0].data["command"] == "Write a Python function to calculate fibonacci numbers"

    # Verify event persisted
    events = event_store.get_all()
    # Should have 2 events: AGENT_CREATED and AGENT_COMMANDED
    assert len(events) == 2
    commanded_event = events[1]
    assert commanded_event["type"] == AGENT_COMMANDED
    assert commanded_event["data"]["agent_name"] == "alice"
    assert commanded_event["data"]["command"] == "Write a Python function to calculate fibonacci numbers"
    assert commanded_event["aggregate_id"] == "alice"
    assert commanded_event["aggregate_type"] == "agent"
    assert "timestamp" in commanded_event["data"]


def test_handle_command_agent_nonexistent_error(command_handler):
    """Test that commanding nonexistent agent raises error."""
    with pytest.raises(ValueError, match="Agent 'bob' does not exist"):
        command_handler.handle_command_agent(
            agent_name="bob",
            command="Do something"
        )


def test_handle_command_agent_timestamp_populated(command_handler, event_store):
    """Test that command timestamp is populated."""
    # Create agent
    command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )

    # Command agent
    before = datetime.utcnow()
    command_handler.handle_command_agent(
        agent_name="alice",
        command="Do something"
    )
    after = datetime.utcnow()

    # Check timestamp
    events = event_store.get_all()
    commanded_event = events[1]
    timestamp = datetime.fromisoformat(commanded_event["data"]["timestamp"])
    assert before <= timestamp <= after


# ═══════════════════════════════════════════════════════════
# USER MESSAGE TESTS
# ═══════════════════════════════════════════════════════════

def test_handle_user_message(command_handler, event_store):
    """Test handling user message."""
    # Send user message
    event_ids, effects = command_handler.handle_user_message(
        message="Hello, orchestrator! Please help me with a task."
    )

    # Verify event IDs returned
    assert len(event_ids) == 1
    assert isinstance(event_ids[0], int)
    assert event_ids[0] > 0

    # Verify effects returned
    assert len(effects) == 1
    assert isinstance(effects[0], Effect)
    assert effects[0].type == "execute_orchestrator"
    assert effects[0].data["message"] == "Hello, orchestrator! Please help me with a task."

    # Verify event persisted
    events = event_store.get_all()
    assert len(events) == 1
    event = events[0]
    assert event["type"] == USER_MESSAGE_RECEIVED
    assert event["data"]["sender"] == "user"
    assert event["data"]["receiver"] == "orchestrator"
    assert event["data"]["message"] == "Hello, orchestrator! Please help me with a task."
    assert event["aggregate_type"] == "chat"
    assert "timestamp" in event["data"]


def test_handle_user_message_timestamp_populated(command_handler, event_store):
    """Test that user message timestamp is populated."""
    before = datetime.utcnow()
    command_handler.handle_user_message(message="Hello!")
    after = datetime.utcnow()

    events = event_store.get_all()
    timestamp = datetime.fromisoformat(events[0]["data"]["timestamp"])
    assert before <= timestamp <= after


def test_handle_user_message_updates_state(command_handler, state_manager):
    """Test that user message updates state manager."""
    # Send message
    command_handler.handle_user_message(message="Hello!")

    # Verify state updated
    state = state_manager.get_state()
    assert len(state.chat_history) == 1
    msg = state.chat_history[0]
    assert msg.sender == "user"
    assert msg.receiver == "orchestrator"
    assert msg.message == "Hello!"


# ═══════════════════════════════════════════════════════════
# EVENTS PERSISTED TESTS
# ═══════════════════════════════════════════════════════════

def test_events_persisted_in_store(command_handler, event_store):
    """Test that all commands persist events to store."""
    # Create agent
    command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )

    # Command agent
    command_handler.handle_command_agent(
        agent_name="alice",
        command="Do something"
    )

    # Send user message
    command_handler.handle_user_message(message="Hello!")

    # Verify all events persisted
    events = event_store.get_all()
    assert len(events) == 3

    # Verify event types
    assert events[0]["type"] == AGENT_CREATED
    assert events[1]["type"] == AGENT_COMMANDED
    assert events[2]["type"] == USER_MESSAGE_RECEIVED

    # Verify events have IDs
    assert all(event["id"] > 0 for event in events)

    # Verify events have timestamps
    assert all(event["timestamp"] > 0 for event in events)


def test_multiple_agents_can_be_created(command_handler, state_manager):
    """Test that multiple agents can be created."""
    # Create multiple agents
    command_handler.handle_create_agent("alice", "You are Alice", "claude-3-5-sonnet-20241022")
    command_handler.handle_create_agent("bob", "You are Bob", "claude-3-5-sonnet-20241022")
    command_handler.handle_create_agent("charlie", "You are Charlie", "claude-3-5-sonnet-20241022")

    # Verify all in state
    state = state_manager.get_state()
    assert len(state.agents) == 3
    assert "alice" in state.agents
    assert "bob" in state.agents
    assert "charlie" in state.agents


def test_command_handler_is_pure(command_handler, event_store, state_manager):
    """Test that command handler maintains pure function semantics."""
    # Get initial state
    initial_state = state_manager.get_state()

    # Create agent
    event_ids, effects = command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )

    # Verify command handler doesn't modify passed objects
    # Effects should be new objects
    assert isinstance(effects[0], Effect)
    assert effects[0].type == "create_claude_client"

    # Verify state was not mutated (new state created)
    new_state = state_manager.get_state()
    assert initial_state is not new_state  # Different objects
    assert len(initial_state.agents) == 0  # Original unchanged
    assert len(new_state.agents) == 1  # New state has agent


# ═══════════════════════════════════════════════════════════
# EFFECT VALIDATION TESTS
# ═══════════════════════════════════════════════════════════

def test_create_agent_effect_has_required_fields(command_handler):
    """Test that create_agent effect has all required fields."""
    _, effects = command_handler.handle_create_agent(
        name="alice",
        system_prompt="You are Alice",
        model="claude-3-5-sonnet-20241022"
    )

    effect = effects[0]
    assert "agent_name" in effect.data
    assert "model" in effect.data
    assert "system_prompt" in effect.data


def test_command_agent_effect_has_required_fields(command_handler):
    """Test that command_agent effect has all required fields."""
    command_handler.handle_create_agent("alice", "You are Alice", "claude-3-5-sonnet-20241022")

    _, effects = command_handler.handle_command_agent(
        agent_name="alice",
        command="Do something"
    )

    effect = effects[0]
    assert "agent_name" in effect.data
    assert "command" in effect.data


def test_user_message_effect_has_required_fields(command_handler):
    """Test that user_message effect has all required fields."""
    _, effects = command_handler.handle_user_message(message="Hello!")

    effect = effects[0]
    assert "message" in effect.data
