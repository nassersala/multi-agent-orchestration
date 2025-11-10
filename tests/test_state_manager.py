"""
Tests for StateManager with rebuild and sync capabilities.

These tests verify:
- State rebuilding from events
- Incremental sync
- Thread safety
- Query methods (get_state, get_agents, get_agent, get_chat_history)
"""

import pytest
import threading
import time
from datetime import datetime

from backend.event_store import EventStore
from backend.state_manager import StateManager
from backend.event_types import (
    ORCHESTRATOR_INITIALIZED,
    AGENT_CREATED,
    AGENT_STATUS_CHANGED,
    AGENT_DELETED,
    COST_INCURRED,
    USER_MESSAGE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED,
)


class TestStateManagerBasics:
    """Test basic state manager initialization and rebuild."""

    def test_rebuild_from_empty_store(self):
        """StateManager should initialize with empty state when no events exist."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        state = manager.get_state()
        assert state.orchestrator_id is None
        assert len(state.agents) == 0
        assert len(state.chat_history) == 0
        assert state.total_cost == 0.0

    def test_rebuild_from_existing_events(self):
        """StateManager should rebuild state from existing events on init."""
        store = EventStore(":memory:")

        # Add events to store before creating manager
        store.append(
            ORCHESTRATOR_INITIALIZED,
            {"orchestrator_id": "orch_123", "session_id": "sess_456"}
        )
        store.append(
            AGENT_CREATED,
            {"name": "alice", "model": "sonnet", "system_prompt": "You are Alice"}
        )
        store.append(
            AGENT_CREATED,
            {"name": "bob", "model": "haiku", "system_prompt": "You are Bob"}
        )

        # Create manager - should rebuild from these events
        manager = StateManager(store)
        state = manager.get_state()

        assert state.orchestrator_id == "orch_123"
        assert state.session_id == "sess_456"
        assert len(state.agents) == 2
        assert "alice" in state.agents
        assert "bob" in state.agents
        assert state.agents["alice"].model == "sonnet"
        assert state.agents["bob"].model == "haiku"

    def test_get_state_returns_current_state(self):
        """get_state() should return the current OrchestratorState."""
        store = EventStore(":memory:")
        store.append(ORCHESTRATOR_INITIALIZED, {"orchestrator_id": "orch_999"})

        manager = StateManager(store)
        state = manager.get_state()

        assert state.orchestrator_id == "orch_999"
        # Verify it's the actual OrchestratorState type
        from backend.models import OrchestratorState
        assert isinstance(state, OrchestratorState)


class TestStateManagerSync:
    """Test incremental sync functionality."""

    def test_sync_applies_new_events(self):
        """sync() should apply events added after initialization."""
        store = EventStore(":memory:")
        store.append(ORCHESTRATOR_INITIALIZED, {"orchestrator_id": "orch_1"})

        manager = StateManager(store)
        assert len(manager.get_agents()) == 0

        # Add new events after manager initialization
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(AGENT_CREATED, {"name": "bob", "model": "haiku"})

        # Sync should apply these new events
        count = manager.sync()
        assert count == 2

        agents = manager.get_agents()
        assert len(agents) == 2
        assert "alice" in agents
        assert "bob" in agents

    def test_sync_returns_event_count(self):
        """sync() should return the number of events applied."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        # No new events
        assert manager.sync() == 0

        # Add 3 events
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(AGENT_CREATED, {"name": "bob", "model": "haiku"})
        store.append(AGENT_STATUS_CHANGED, {"agent_name": "alice", "new_status": "executing"})

        assert manager.sync() == 3

        # Sync again - no new events
        assert manager.sync() == 0

    def test_sync_multiple_times(self):
        """Multiple sync() calls should correctly track last_event_id."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        # First sync
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        assert manager.sync() == 1
        assert "alice" in manager.get_agents()

        # Second sync
        store.append(AGENT_CREATED, {"name": "bob", "model": "haiku"})
        assert manager.sync() == 1
        assert "bob" in manager.get_agents()

        # Third sync
        store.append(AGENT_STATUS_CHANGED, {"agent_name": "alice", "new_status": "executing"})
        assert manager.sync() == 1
        assert manager.get_agent("alice").status == "executing"

    def test_sync_preserves_event_order(self):
        """Events should be applied in order during sync."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        # Create agent, change status, delete agent
        store.append(AGENT_CREATED, {"name": "temp", "model": "sonnet"})
        store.append(AGENT_STATUS_CHANGED, {"agent_name": "temp", "new_status": "executing"})
        store.append(AGENT_DELETED, {"agent_name": "temp"})

        manager.sync()

        # Agent should not exist after deletion
        assert manager.get_agent("temp") is None
        assert "temp" not in manager.get_agents()


class TestStateManagerAgentQueries:
    """Test agent query methods."""

    def test_get_agents_returns_dict(self):
        """get_agents() should return a dictionary of all agents."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(AGENT_CREATED, {"name": "bob", "model": "haiku"})

        manager = StateManager(store)
        agents = manager.get_agents()

        assert isinstance(agents, dict)
        assert len(agents) == 2
        assert "alice" in agents
        assert "bob" in agents

        from backend.models import Agent
        assert isinstance(agents["alice"], Agent)

    def test_get_agent_by_name_exists(self):
        """get_agent(name) should return agent when it exists."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet", "system_prompt": "Hello"})

        manager = StateManager(store)
        agent = manager.get_agent("alice")

        assert agent is not None
        assert agent.name == "alice"
        assert agent.model == "sonnet"
        assert agent.system_prompt == "Hello"

    def test_get_agent_by_name_not_found(self):
        """get_agent(name) should return None when agent doesn't exist."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})

        manager = StateManager(store)
        agent = manager.get_agent("nonexistent")

        assert agent is None

    def test_get_agents_after_deletion(self):
        """get_agents() should not include deleted agents."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(AGENT_CREATED, {"name": "bob", "model": "haiku"})
        store.append(AGENT_DELETED, {"agent_name": "alice"})

        manager = StateManager(store)
        agents = manager.get_agents()

        assert len(agents) == 1
        assert "alice" not in agents
        assert "bob" in agents


class TestStateManagerChatHistory:
    """Test chat history query methods."""

    def test_get_chat_history_all(self):
        """get_chat_history() with no limit should return all messages."""
        store = EventStore(":memory:")
        store.append(USER_MESSAGE_RECEIVED, {"message": "Hello"})
        store.append(ORCHESTRATOR_RESPONSE_GENERATED, {"message": "Hi there"})
        store.append(USER_MESSAGE_RECEIVED, {"message": "How are you?"})

        manager = StateManager(store)
        history = manager.get_chat_history()

        assert len(history) == 3
        assert history[0].message == "Hello"
        assert history[1].message == "Hi there"
        assert history[2].message == "How are you?"

    def test_get_chat_history_with_limit(self):
        """get_chat_history(limit=N) should return last N messages."""
        store = EventStore(":memory:")
        for i in range(10):
            store.append(USER_MESSAGE_RECEIVED, {"message": f"Message {i}"})

        manager = StateManager(store)
        history = manager.get_chat_history(limit=3)

        assert len(history) == 3
        assert history[0].message == "Message 7"
        assert history[1].message == "Message 8"
        assert history[2].message == "Message 9"

    def test_get_chat_history_limit_exceeds_total(self):
        """get_chat_history with limit > total should return all messages."""
        store = EventStore(":memory:")
        store.append(USER_MESSAGE_RECEIVED, {"message": "Only message"})

        manager = StateManager(store)
        history = manager.get_chat_history(limit=100)

        assert len(history) == 1
        assert history[0].message == "Only message"

    def test_get_chat_history_empty(self):
        """get_chat_history() should return empty list when no messages."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        history = manager.get_chat_history()
        assert history == []

        history_limited = manager.get_chat_history(limit=5)
        assert history_limited == []


class TestStateManagerCostTracking:
    """Test that cost events are properly reflected in state."""

    def test_cost_incurred_updates_state(self):
        """COST_INCURRED events should update state totals."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(
            COST_INCURRED,
            {
                "agent_name": "alice",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.05
            }
        )

        manager = StateManager(store)
        state = manager.get_state()

        # Orchestrator totals
        assert state.total_input_tokens == 100
        assert state.total_output_tokens == 50
        assert state.total_cost == 0.05

        # Agent-specific totals
        alice = manager.get_agent("alice")
        assert alice.input_tokens == 100
        assert alice.output_tokens == 50
        assert alice.total_cost == 0.05

    def test_multiple_cost_events_accumulate(self):
        """Multiple COST_INCURRED events should accumulate."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(COST_INCURRED, {"agent_name": "alice", "input_tokens": 100, "output_tokens": 50, "cost": 0.05})
        store.append(COST_INCURRED, {"agent_name": "alice", "input_tokens": 200, "output_tokens": 100, "cost": 0.10})

        manager = StateManager(store)
        alice = manager.get_agent("alice")

        assert alice.input_tokens == 300
        assert alice.output_tokens == 150
        assert alice.total_cost == pytest.approx(0.15)


class TestStateManagerThreadSafety:
    """Test thread safety of StateManager."""

    def test_concurrent_reads(self):
        """Multiple threads should be able to read state concurrently."""
        store = EventStore(":memory:")
        for i in range(100):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        manager = StateManager(store)
        results = []
        errors = []

        def read_state():
            try:
                for _ in range(100):
                    state = manager.get_state()
                    agents = manager.get_agents()
                    assert len(agents) == 100
                    results.append(True)
            except Exception as e:
                errors.append(e)

        # Start 10 concurrent reader threads
        threads = [threading.Thread(target=read_state) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 1000  # 10 threads * 100 reads each

    def test_sync_while_reading(self):
        """sync() should be safe while other threads are reading."""
        store = EventStore(":memory:")
        manager = StateManager(store)
        errors = []

        def reader():
            try:
                for _ in range(50):
                    state = manager.get_state()
                    agents = manager.get_agents()
                    # Just verify we can read without errors
                    assert isinstance(agents, dict)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(50):
                    store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})
                    manager.sync()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Start reader and writer threads
        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)

        reader_thread.start()
        writer_thread.start()

        reader_thread.join()
        writer_thread.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify final state
        final_state = manager.get_state()
        assert len(final_state.agents) == 50

    def test_get_methods_thread_safe(self):
        """All get methods should be thread-safe."""
        store = EventStore(":memory:")
        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        store.append(USER_MESSAGE_RECEIVED, {"message": "Hello"})

        manager = StateManager(store)
        errors = []

        def access_all_methods():
            try:
                for _ in range(100):
                    manager.get_state()
                    manager.get_agents()
                    manager.get_agent("alice")
                    manager.get_chat_history(limit=10)
            except Exception as e:
                errors.append(e)

        # Run 5 threads concurrently
        threads = [threading.Thread(target=access_all_methods) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"


class TestStateManagerImmutability:
    """Test that state remains immutable."""

    def test_state_is_immutable(self):
        """Returned state should be immutable (frozen dataclass)."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        state = manager.get_state()

        # Attempting to modify should raise error
        with pytest.raises(Exception):  # FrozenInstanceError
            state.orchestrator_id = "modified"

    def test_sync_creates_new_state(self):
        """sync() should create new state instances, not mutate existing."""
        store = EventStore(":memory:")
        manager = StateManager(store)

        state_before = manager.get_state()
        id_before = id(state_before)

        store.append(AGENT_CREATED, {"name": "alice", "model": "sonnet"})
        manager.sync()

        state_after = manager.get_state()
        id_after = id(state_after)

        # Should be different objects
        assert id_before != id_after
        assert len(state_before.agents) == 0
        assert len(state_after.agents) == 1


# ═══════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════

class TestStateManagerIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self):
        """Test complete workflow: init, create agents, send messages, track costs."""
        store = EventStore(":memory:")

        # Initialize orchestrator
        store.append(
            ORCHESTRATOR_INITIALIZED,
            {"orchestrator_id": "orch_main", "session_id": "sess_123"}
        )

        # Create state manager
        manager = StateManager(store)

        # Verify initialization
        state = manager.get_state()
        assert state.orchestrator_id == "orch_main"
        assert state.session_id == "sess_123"

        # Add agents
        store.append(AGENT_CREATED, {"name": "researcher", "model": "sonnet"})
        store.append(AGENT_CREATED, {"name": "coder", "model": "sonnet"})
        manager.sync()

        assert len(manager.get_agents()) == 2

        # Send messages
        store.append(USER_MESSAGE_RECEIVED, {"message": "Research topic X"})
        store.append(ORCHESTRATOR_RESPONSE_GENERATED, {"message": "Assigning to researcher"})
        manager.sync()

        history = manager.get_chat_history()
        assert len(history) == 2

        # Track costs
        store.append(
            COST_INCURRED,
            {"agent_name": "researcher", "input_tokens": 500, "output_tokens": 300, "cost": 0.20}
        )
        manager.sync()

        state = manager.get_state()
        assert state.total_input_tokens == 500
        assert state.total_output_tokens == 300
        assert state.total_cost == 0.20

        researcher = manager.get_agent("researcher")
        assert researcher.total_cost == 0.20

        # Change agent status
        store.append(AGENT_STATUS_CHANGED, {"agent_name": "researcher", "new_status": "executing"})
        manager.sync()

        researcher = manager.get_agent("researcher")
        assert researcher.status == "executing"

        # Delete agent
        store.append(AGENT_DELETED, {"agent_name": "coder"})
        manager.sync()

        assert len(manager.get_agents()) == 1
        assert manager.get_agent("coder") is None
        assert manager.get_agent("researcher") is not None
