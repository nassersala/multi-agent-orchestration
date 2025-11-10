"""
Integration tests for Claude SDK.

These tests require ANTHROPIC_API_KEY and claude-agent-sdk to be installed.
Run with: pytest tests/test_claude_integration.py -v -m integration

To skip these tests: pytest -v -m "not integration"
"""

import pytest
import os

from backend.event_store import EventStore
from backend.effect_executor import EffectExecutor, CLAUDE_SDK_AVAILABLE
from backend.effects import Effect
from backend.event_types import (
    AGENT_STATUS_CHANGED,
    AGENT_RESPONSE_RECEIVED,
    COST_INCURRED,
    TOOL_INVOKED,
)


# Skip all integration tests if SDK not available or no API key
pytestmark = pytest.mark.integration


@pytest.fixture
def has_claude_sdk():
    """Check if Claude SDK is available."""
    if not CLAUDE_SDK_AVAILABLE:
        pytest.skip("claude-agent-sdk not installed")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")


@pytest.fixture
def event_store():
    """Create in-memory event store for testing."""
    return EventStore(":memory:")


@pytest.fixture
def effect_executor_real(event_store, has_claude_sdk):
    """Create effect executor with real SDK."""
    return EffectExecutor(event_store, use_mock=False)


# ═══════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_real_sdk_agent_execution(effect_executor_real, event_store):
    """
    Test real Claude SDK agent execution.

    This test uses real API calls and incurs costs.
    """
    # Create agent
    create_effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "test_agent",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are a helpful test agent. Keep responses very brief.",
        }
    )
    await effect_executor_real.execute([create_effect])

    # Execute simple command
    command_effect = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "test_agent",
            "command": "What is 2+2? Answer with just the number.",
        }
    )
    await effect_executor_real.execute([command_effect])

    # Verify events
    events = event_store.get_all()

    # Should have: client_created, executing, response(s), cost, idle
    assert len(events) >= 4

    # Check we got status changes
    status_events = [e for e in events if e["type"] == AGENT_STATUS_CHANGED]
    assert len(status_events) >= 2  # At least executing and idle

    # Check we got a response
    response_events = [e for e in events if e["type"] == AGENT_RESPONSE_RECEIVED]
    assert len(response_events) >= 1

    # Check we got cost tracking
    cost_events = [e for e in events if e["type"] == COST_INCURRED]
    assert len(cost_events) == 1
    cost_event = cost_events[0]
    assert cost_event["data"]["input_tokens"] > 0
    assert cost_event["data"]["output_tokens"] > 0
    assert cost_event["data"]["cost"] > 0


@pytest.mark.asyncio
async def test_real_sdk_session_resume(effect_executor_real, event_store):
    """
    Test that sessions can be resumed.

    This test uses real API calls and incurs costs.
    """
    # Create agent
    create_effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "test_agent",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are a helpful test agent.",
        }
    )
    await effect_executor_real.execute([create_effect])

    # First command
    command1 = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "test_agent",
            "command": "Remember the number 42.",
        }
    )
    await effect_executor_real.execute([command1])

    # Check session ID was stored
    agent_config = effect_executor_real._claude_clients.get("test_agent")
    assert agent_config is not None
    assert agent_config.get("session_id") is not None

    # Second command (should resume session)
    command2 = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "test_agent",
            "command": "What number did I ask you to remember?",
        }
    )
    await effect_executor_real.execute([command2])

    # Verify both commands executed
    events = event_store.get_all()
    response_events = [e for e in events if e["type"] == AGENT_RESPONSE_RECEIVED]
    # Should have responses from both commands
    assert len(response_events) >= 2


@pytest.mark.asyncio
async def test_real_sdk_tool_invocation_logged(effect_executor_real, event_store):
    """
    Test that tool invocations are logged.

    This test uses real API calls and incurs costs.
    """
    # Create agent
    create_effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "test_agent",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "You are a helpful test agent with access to tools.",
        }
    )
    await effect_executor_real.execute([create_effect])

    # Command that might trigger tool use (though not guaranteed)
    command_effect = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "test_agent",
            "command": "Read the README.md file if it exists, otherwise just say hello.",
        }
    )
    await effect_executor_real.execute([command_effect])

    # Check for any tool invocations (may or may not happen)
    events = event_store.get_all()
    tool_events = [e for e in events if e["type"] == TOOL_INVOKED]

    # If tools were used, verify structure
    for tool_event in tool_events:
        assert "tool_name" in tool_event["data"]
        assert "tool_input" in tool_event["data"]
        assert "agent_name" in tool_event["data"]


@pytest.mark.asyncio
async def test_real_sdk_error_handling(effect_executor_real, event_store):
    """
    Test error handling with real SDK.

    This test uses real API calls and incurs costs.
    """
    # Try to command non-existent agent
    command_effect = Effect(
        type="execute_agent_command",
        data={
            "agent_name": "nonexistent_agent",
            "command": "Do something",
        }
    )

    # Should fail but be caught and logged
    await effect_executor_real.execute([command_effect])

    # Check for error event
    events = event_store.get_all()
    # Should have effect execution failed event
    # (The error is caught in execute() method)
    # Since the agent doesn't exist, _execute_agent_command_real will raise ValueError
    # which gets caught and logged as EFFECT_EXECUTION_FAILED
    from backend.event_types import EFFECT_EXECUTION_FAILED
    error_events = [e for e in events if e["type"] == EFFECT_EXECUTION_FAILED]
    assert len(error_events) >= 1


# ═══════════════════════════════════════════════════════════
# MOCK VS REAL MODE TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mock_mode_explicit():
    """Test that mock mode can be explicitly enabled."""
    event_store = EventStore(":memory:")
    executor = EffectExecutor(event_store, use_mock=True)

    assert executor._use_mock is True

    # Should work without API key
    create_effect = Effect(
        type="create_claude_client",
        data={
            "agent_name": "test",
            "model": "claude-3-5-sonnet-20241022",
            "system_prompt": "Test",
        }
    )
    await executor.execute([create_effect])

    # Should have created mock client
    assert "test" in executor._claude_clients


@pytest.mark.asyncio
async def test_auto_detect_mode_without_api_key():
    """Test that auto-detect uses mock mode without API key."""
    # Temporarily remove API key
    original_key = os.environ.pop("ANTHROPIC_API_KEY", None)

    try:
        event_store = EventStore(":memory:")
        executor = EffectExecutor(event_store)  # Auto-detect

        # Should default to mock mode
        assert executor._use_mock is True
    finally:
        # Restore API key
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key
