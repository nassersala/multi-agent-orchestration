"""
Tests for effect executor.

Tests effect execution, error handling, and event logging.
All tests use real EventStore (no mocks).
"""

import pytest
import asyncio
from datetime import datetime

from backend.event_store import EventStore
from backend.effect_executor import EffectExecutor
from backend.effects import Effect
from backend.event_types import (
    AGENT_STATUS_CHANGED,
    AGENT_RESPONSE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED,
    EFFECT_EXECUTION_FAILED,
    COST_INCURRED,
)


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def event_store():
    """Create in-memory event store for testing."""
    return EventStore(":memory:")


@pytest.fixture
def effect_executor(event_store):
    """Create effect executor with in-memory store in mock mode."""
    return EffectExecutor(event_store, use_mock=True)


# ═══════════════════════════════════════════════════════════
# CREATE CLAUDE CLIENT TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_execute_create_claude_client(effect_executor, event_store):
    """Test executing create_claude_client effect."""
    # Create effect
    effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "alice",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are Alice",
            "template": None,
        }
    )

    # Execute effect
    await effect_executor.execute([effect])

    # Verify client created
    assert "alice" in effect_executor._claude_clients
    client = effect_executor._claude_clients["alice"]
    assert client["model"] == "claude-3-5-sonnet-20241022"
    assert client["system_prompt"] == "You are Alice"

    # Verify event logged
    events = event_store.get_all()
    assert len(events) == 1
    assert events[0]["type"] == AGENT_STATUS_CHANGED
    assert events[0]["data"]["agent_name"] == "alice"
    assert events[0]["data"]["reason"] == "client_created"


@pytest.mark.asyncio
async def test_create_claude_client_with_template(effect_executor, event_store):
    """Test creating client with template."""
    effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "bob",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are Bob",
            "template": "code_reviewer",
        }
    )

    await effect_executor.execute([effect])

    # Verify template stored
    client = effect_executor._claude_clients["bob"]
    assert client["template"] == "code_reviewer"


# ═══════════════════════════════════════════════════════════
# EXECUTE AGENT COMMAND TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_execute_agent_command(effect_executor, event_store):
    """Test executing agent_command effect."""
    # Create client first
    create_effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "alice",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are Alice",
        }
    )
    await effect_executor.execute([create_effect])

    # Clear events from client creation
    initial_event_count = len(event_store.get_all())

    # Execute command
    command_effect = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "alice",
            "command": "Write a Python function",
        }
    )
    await effect_executor.execute([command_effect])

    # Verify events logged
    events = event_store.get_all()[initial_event_count:]

    # Should have 4 events: status->executing, response, cost, status->idle
    assert len(events) == 4

    # Check status change to executing
    assert events[0]["type"] == AGENT_STATUS_CHANGED
    assert events[0]["data"]["agent_name"] == "alice"
    assert events[0]["data"]["new_status"] == "executing"

    # Check response
    assert events[1]["type"] == AGENT_RESPONSE_RECEIVED
    assert events[1]["data"]["agent_name"] == "alice"
    assert "Mock response" in events[1]["data"]["response"]

    # Check cost
    assert events[2]["type"] == COST_INCURRED
    assert events[2]["data"]["agent_name"] == "alice"
    assert events[2]["data"]["input_tokens"] == 100
    assert events[2]["data"]["output_tokens"] == 50
    assert events[2]["data"]["cost"] == 0.0015

    # Check status change to idle
    assert events[3]["type"] == AGENT_STATUS_CHANGED
    assert events[3]["data"]["agent_name"] == "alice"
    assert events[3]["data"]["new_status"] == "idle"


@pytest.mark.asyncio
async def test_agent_command_response_contains_command(effect_executor, event_store):
    """Test that agent response references the command."""
    # Create client
    create_effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "alice",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are Alice",
        }
    )
    await effect_executor.execute([create_effect])

    # Execute command with specific text
    command_effect = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "alice",
            "command": "Calculate fibonacci numbers",
        }
    )
    await effect_executor.execute([command_effect])

    # Find response event
    events = event_store.get_all()
    response_events = [e for e in events if e["type"] == AGENT_RESPONSE_RECEIVED]
    assert len(response_events) == 1
    assert "Calculate fibonacci" in response_events[0]["data"]["response"]


# ═══════════════════════════════════════════════════════════
# EXECUTE ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_execute_orchestrator(effect_executor, event_store):
    """Test executing orchestrator effect."""
    # Execute orchestrator
    effect = Effect(
        type="execute_orchestrator",
        data={
            "message": "Hello, how can you help me?",
        }
    )
    await effect_executor.execute([effect])

    # Verify events logged
    events = event_store.get_all()

    # Should have 2 events: response, cost
    assert len(events) == 2

    # Check response
    assert events[0]["type"] == ORCHESTRATOR_RESPONSE_GENERATED
    assert events[0]["data"]["sender"] == "orchestrator"
    assert events[0]["data"]["receiver"] == "user"
    assert "Mock orchestrator response" in events[0]["data"]["message"]
    assert "Hello" in events[0]["data"]["message"]

    # Check cost
    assert events[1]["type"] == COST_INCURRED
    assert events[1]["data"]["agent_name"] == "orchestrator"
    assert events[1]["data"]["input_tokens"] == 200
    assert events[1]["data"]["output_tokens"] == 100
    assert events[1]["data"]["cost"] == 0.003


@pytest.mark.asyncio
async def test_orchestrator_response_references_message(effect_executor, event_store):
    """Test that orchestrator response references user message."""
    effect = Effect(
        type="execute_orchestrator",
        data={
            "message": "Tell me about quantum computing",
        }
    )
    await effect_executor.execute([effect])

    # Find response event
    events = event_store.get_all()
    response_events = [e for e in events if e["type"] == ORCHESTRATOR_RESPONSE_GENERATED]
    assert len(response_events) == 1
    assert "Tell me about quantum" in response_events[0]["data"]["message"]


# ═══════════════════════════════════════════════════════════
# ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_effect_execution_error(effect_executor, event_store):
    """Test that effect execution errors are logged."""
    # Create effect with unknown type
    effect = Effect(
        type="unknown_effect_type",  # type: ignore
        data={"foo": "bar"}
    )

    # Execute effect (should catch error)
    await effect_executor.execute([effect])

    # Verify error event logged
    events = event_store.get_all()
    assert len(events) == 1
    assert events[0]["type"] == EFFECT_EXECUTION_FAILED
    assert events[0]["data"]["effect_type"] == "unknown_effect_type"
    assert "Unknown effect type" in events[0]["data"]["error"]
    assert "traceback" in events[0]["data"]


@pytest.mark.asyncio
async def test_error_does_not_stop_subsequent_effects(effect_executor, event_store):
    """Test that error in one effect doesn't stop execution of others."""
    effects = [
        Effect(type="unknown_type_1", data={}),  # type: ignore
        Effect(
            type="create_claude_client",
            data={
                "agent_name": "alice",
                "model": "claude-3-5-sonnet-20241022",
                "system_prompt": "You are Alice",
            }
        ),
        Effect(type="unknown_type_2", data={}),  # type: ignore
    ]

    # Execute all effects
    await effect_executor.execute(effects)

    # Verify we have events from both errors and successful execution
    events = event_store.get_all()
    error_events = [e for e in events if e["type"] == EFFECT_EXECUTION_FAILED]
    success_events = [e for e in events if e["type"] == AGENT_STATUS_CHANGED]

    assert len(error_events) == 2  # Two errors
    assert len(success_events) == 1  # One success


@pytest.mark.asyncio
async def test_error_includes_traceback(effect_executor, event_store):
    """Test that error events include full traceback."""
    effect = Effect(
        type="unknown_effect",  # type: ignore
        data={"test": "data"}
    )

    await effect_executor.execute([effect])

    events = event_store.get_all()
    error_event = events[0]
    assert error_event["type"] == EFFECT_EXECUTION_FAILED
    assert "traceback" in error_event["data"]
    assert "ValueError" in error_event["data"]["traceback"]


# ═══════════════════════════════════════════════════════════
# MULTIPLE EFFECTS TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_multiple_effects_in_sequence(effect_executor, event_store):
    """Test executing multiple effects in sequence."""
    effects = [
        Effect(
            type="create_claude_client",
            data={
                "agent_name": "alice",
                "model": "claude-3-5-sonnet-20241022",
                "system_prompt": "You are Alice",
            }
        ),
        Effect(
            type="create_claude_client",
            data={
                "agent_name": "bob",
                "model": "claude-3-5-sonnet-20241022",
                "system_prompt": "You are Bob",
            }
        ),
        Effect(
            type="execute_agent_command",
            data={
                "agent_name": "alice",
                "command": "Do task A",
            }
        ),
        Effect(
            type="execute_orchestrator",
            data={
                "message": "Status update",
            }
        ),
    ]

    # Execute all effects
    await effect_executor.execute(effects)

    # Verify all effects executed
    assert len(effect_executor._claude_clients) == 2
    assert "alice" in effect_executor._claude_clients
    assert "bob" in effect_executor._claude_clients

    # Verify events from all effects
    events = event_store.get_all()

    # Should have events from all 4 effects
    agent_created_events = [e for e in events if e["type"] == AGENT_STATUS_CHANGED and e["data"].get("reason") == "client_created"]
    agent_command_events = [e for e in events if e["type"] == AGENT_RESPONSE_RECEIVED]
    orchestrator_events = [e for e in events if e["type"] == ORCHESTRATOR_RESPONSE_GENERATED]

    assert len(agent_created_events) == 2  # alice and bob created
    assert len(agent_command_events) == 1  # alice executed
    assert len(orchestrator_events) == 1  # orchestrator executed


@pytest.mark.asyncio
async def test_effects_execute_in_order(effect_executor, event_store):
    """Test that effects execute in the order provided."""
    effects = [
        Effect(
            type="execute_orchestrator",
            data={"message": "First"},
        ),
        Effect(
            type="execute_orchestrator",
            data={"message": "Second"},
        ),
        Effect(
            type="execute_orchestrator",
            data={"message": "Third"},
        ),
    ]

    await effect_executor.execute(effects)

    # Check order of responses
    events = event_store.get_all()
    response_events = [e for e in events if e["type"] == ORCHESTRATOR_RESPONSE_GENERATED]

    assert len(response_events) == 3
    assert "First" in response_events[0]["data"]["message"]
    assert "Second" in response_events[1]["data"]["message"]
    assert "Third" in response_events[2]["data"]["message"]


# ═══════════════════════════════════════════════════════════
# TIMESTAMP TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_events_have_timestamps(effect_executor, event_store):
    """Test that all logged events have timestamps."""
    effects = [
        Effect(
            type="create_claude_client",
            data={
                "agent_name": "alice",
                "model": "claude-3-5-sonnet-20241022",
                "system_prompt": "You are Alice",
            }
        ),
        Effect(
            type="execute_agent_command",
            data={
                "agent_name": "alice",
                "command": "Do something",
            }
        ),
        Effect(
            type="execute_orchestrator",
            data={"message": "Hello"},
        ),
    ]

    before = datetime.utcnow()
    await effect_executor.execute(effects)
    after = datetime.utcnow()

    # Check all events have valid timestamps
    events = event_store.get_all()
    for event in events:
        assert "timestamp" in event["data"]
        timestamp = datetime.fromisoformat(event["data"]["timestamp"])
        assert before <= timestamp <= after


# ═══════════════════════════════════════════════════════════
# AGGREGATE TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_events_have_correct_aggregates(effect_executor, event_store):
    """Test that events are tagged with correct aggregate IDs and types."""
    effects = [
        Effect(
            type="create_claude_client",
            data={
                "agent_name": "alice",
                "model": "claude-3-5-sonnet-20241022",
                "system_prompt": "You are Alice",
            }
        ),
        Effect(
            type="execute_agent_command",
            data={
                "agent_name": "alice",
                "command": "Do something",
            }
        ),
    ]

    await effect_executor.execute(effects)

    # Check aggregates
    events = event_store.get_all()
    agent_events = [e for e in events if e.get("aggregate_type") == "agent"]

    # All agent events should have aggregate_id "alice"
    for event in agent_events:
        assert event["aggregate_id"] == "alice"
        assert event["aggregate_type"] == "agent"
