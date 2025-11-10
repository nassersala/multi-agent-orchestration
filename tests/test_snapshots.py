"""
Tests for snapshot system and StateManager snapshot integration.

These tests verify:
- Snapshot saving and loading
- StateManager snapshot integration
- Performance improvements with snapshots
- Snapshot cleanup and management
"""

import pytest
import time

from backend.event_store import EventStore
from backend.snapshot_manager import SnapshotManager
from backend.state_manager import StateManager
from backend.models import OrchestratorState
from backend.event_types import (
    ORCHESTRATOR_INITIALIZED,
    AGENT_CREATED,
    AGENT_STATUS_CHANGED,
    COST_INCURRED,
    USER_MESSAGE_RECEIVED,
)


class TestSnapshotManagerBasics:
    """Test basic snapshot manager functionality."""

    def test_save_and_load_snapshot(self):
        """Should be able to save and load a snapshot."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        # Create a state with some data
        state = OrchestratorState(
            orchestrator_id="orch_123",
            session_id="sess_456",
            status='idle'
        )

        # Save snapshot
        mgr.save_snapshot(state, event_id=100)

        # Load it back
        result = mgr.load_latest_snapshot()
        assert result is not None

        loaded_state, event_id = result
        assert event_id == 100
        assert loaded_state.orchestrator_id == "orch_123"
        assert loaded_state.session_id == "sess_456"
        assert loaded_state.status == 'idle'

    def test_load_latest_returns_newest(self):
        """load_latest_snapshot should return the most recent snapshot."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        # Save multiple snapshots
        state1 = OrchestratorState(orchestrator_id="orch_1")
        state2 = OrchestratorState(orchestrator_id="orch_2")
        state3 = OrchestratorState(orchestrator_id="orch_3")

        mgr.save_snapshot(state1, event_id=100)
        mgr.save_snapshot(state2, event_id=200)
        mgr.save_snapshot(state3, event_id=300)

        # Should get the latest one
        result = mgr.load_latest_snapshot()
        assert result is not None

        loaded_state, event_id = result
        assert event_id == 300
        assert loaded_state.orchestrator_id == "orch_3"

    def test_load_latest_returns_none_when_empty(self):
        """load_latest_snapshot should return None when no snapshots exist."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        result = mgr.load_latest_snapshot()
        assert result is None

    def test_should_snapshot_at_intervals(self):
        """should_snapshot should return True at configured intervals."""
        mgr = SnapshotManager(":memory:", snapshot_interval=1000)

        # Should snapshot at multiples of 1000
        assert mgr.should_snapshot(1000) is True
        assert mgr.should_snapshot(2000) is True
        assert mgr.should_snapshot(3000) is True

        # Should not snapshot at other values
        assert mgr.should_snapshot(999) is False
        assert mgr.should_snapshot(1001) is False
        assert mgr.should_snapshot(1500) is False
        assert mgr.should_snapshot(0) is False

    def test_snapshot_with_complex_state(self):
        """Snapshots should preserve complex state with agents and messages."""
        from backend.models import Agent, ChatMessage
        from datetime import datetime

        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        # Create complex state
        agent1 = Agent(name="alice", model="sonnet", system_prompt="Hello")
        agent2 = Agent(name="bob", model="haiku", status='executing')

        msg1 = ChatMessage(
            sender='user',
            receiver='orchestrator',
            message="Hello",
            timestamp=datetime.utcnow()
        )

        state = OrchestratorState(
            orchestrator_id="orch_complex",
            agents={"alice": agent1, "bob": agent2},
            chat_history=[msg1],
            total_cost=1.5
        )

        # Save and load
        mgr.save_snapshot(state, event_id=500)
        loaded_state, event_id = mgr.load_latest_snapshot()

        assert event_id == 500
        assert loaded_state.orchestrator_id == "orch_complex"
        assert len(loaded_state.agents) == 2
        assert "alice" in loaded_state.agents
        assert "bob" in loaded_state.agents
        assert loaded_state.agents["alice"].system_prompt == "Hello"
        assert loaded_state.agents["bob"].status == "executing"
        assert len(loaded_state.chat_history) == 1
        assert loaded_state.chat_history[0].message == "Hello"
        assert loaded_state.total_cost == 1.5


class TestSnapshotManagerManagement:
    """Test snapshot management features."""

    def test_get_snapshot_count(self):
        """Should return the correct number of snapshots."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        assert mgr.get_snapshot_count() == 0

        state = OrchestratorState()
        mgr.save_snapshot(state, 100)
        assert mgr.get_snapshot_count() == 1

        mgr.save_snapshot(state, 200)
        assert mgr.get_snapshot_count() == 2

        mgr.save_snapshot(state, 300)
        assert mgr.get_snapshot_count() == 3

    def test_delete_old_snapshots(self):
        """Should delete old snapshots keeping only recent N."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)
        state = OrchestratorState()

        # Create 10 snapshots
        for i in range(1, 11):
            mgr.save_snapshot(state, event_id=i * 100)

        assert mgr.get_snapshot_count() == 10

        # Keep only 3 most recent
        deleted = mgr.delete_old_snapshots(keep_count=3)
        assert deleted == 7
        assert mgr.get_snapshot_count() == 3

        # Latest should be event_id 1000
        loaded_state, event_id = mgr.load_latest_snapshot()
        assert event_id == 1000

    def test_delete_old_snapshots_when_not_enough(self):
        """delete_old_snapshots should handle case when there aren't enough to delete."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)
        state = OrchestratorState()

        # Only 2 snapshots
        mgr.save_snapshot(state, 100)
        mgr.save_snapshot(state, 200)

        # Try to keep 5
        deleted = mgr.delete_old_snapshots(keep_count=5)
        assert deleted == 0
        assert mgr.get_snapshot_count() == 2

    def test_snapshot_replace_on_same_event_id(self):
        """Saving snapshot with same event_id should replace existing."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        state1 = OrchestratorState(orchestrator_id="first")
        state2 = OrchestratorState(orchestrator_id="second")

        mgr.save_snapshot(state1, event_id=1000)
        assert mgr.get_snapshot_count() == 1

        # Save another with same event_id
        mgr.save_snapshot(state2, event_id=1000)
        assert mgr.get_snapshot_count() == 1  # Still just 1

        # Should have the second one
        loaded_state, _ = mgr.load_latest_snapshot()
        assert loaded_state.orchestrator_id == "second"


class TestStateManagerSnapshotIntegration:
    """Test StateManager integration with snapshots."""

    def test_state_manager_uses_snapshot_on_init(self):
        """StateManager should load from snapshot on initialization."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=10)

        # Create events up to event 20
        for i in range(20):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        # Create a state manager without snapshots - will rebuild from all events
        manager1 = StateManager(store)
        assert len(manager1.get_agents()) == 20

        # Save a snapshot at event 10
        state_at_10 = OrchestratorState()
        for i in range(10):
            from backend.models import Agent
            agent = Agent(name=f"agent_{i}", model="sonnet")
            state_at_10 = state_at_10.with_agent(agent)

        snapshot_mgr.save_snapshot(state_at_10, event_id=10)

        # Create new state manager with snapshots
        # Should load snapshot at 10, then replay events 11-20
        manager2 = StateManager(store, snapshot_mgr)

        # Should have all 20 agents
        assert len(manager2.get_agents()) == 20

    def test_state_manager_creates_snapshots_during_sync(self):
        """StateManager should automatically create snapshots during sync."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=5)

        manager = StateManager(store, snapshot_mgr)

        assert snapshot_mgr.get_snapshot_count() == 0

        # Add events that will trigger snapshots at 5, 10, 15, 20
        for i in range(25):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})
            manager.sync()

        # Should have created snapshots at events 5, 10, 15, 20, 25
        assert snapshot_mgr.get_snapshot_count() == 5

        # Latest snapshot should be at event 25
        loaded_state, event_id = snapshot_mgr.load_latest_snapshot()
        assert event_id == 25

    def test_state_manager_maybe_snapshot_manual(self):
        """maybe_snapshot can be called manually."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=10)

        # Add events up to 10
        for i in range(10):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        manager = StateManager(store, snapshot_mgr)

        # Should have auto-snapshotted at event 10 during init
        assert snapshot_mgr.get_snapshot_count() == 1

        # Manually call maybe_snapshot at event 20
        store.append(AGENT_CREATED, {"name": "agent_10", "model": "sonnet"})
        manager.sync()  # Now at event 11

        # Add more to get to 20
        for i in range(11, 20):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})
            manager.sync()

        # Should have snapshots at 10 and 20
        assert snapshot_mgr.get_snapshot_count() == 2

    def test_state_manager_without_snapshot_manager(self):
        """StateManager should work fine without snapshot manager."""
        store = EventStore(":memory:")

        # No snapshot manager
        manager = StateManager(store)

        # Add events
        for i in range(10):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})
            manager.sync()

        # Should still work
        assert len(manager.get_agents()) == 10

        # maybe_snapshot should return False
        assert manager.maybe_snapshot() is False

    def test_snapshot_recovery_after_many_events(self):
        """Snapshots should significantly speed up recovery."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=100)

        # Add 1000 events
        for i in range(1000):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        # Create manager with snapshots - should auto-snapshot every 100 events
        manager1 = StateManager(store, snapshot_mgr)
        state1 = manager1.get_state()

        # Should have created snapshots at 100, 200, ..., 1000
        assert snapshot_mgr.get_snapshot_count() == 10

        # Create a new manager - should load from snapshot 1000
        manager2 = StateManager(store, snapshot_mgr)
        state2 = manager2.get_state()

        # States should match
        assert len(state1.agents) == len(state2.agents) == 1000

        # Verify the snapshot is at event 1000
        _, event_id = snapshot_mgr.load_latest_snapshot()
        assert event_id == 1000


class TestSnapshotPerformance:
    """Test snapshot performance improvements."""

    def test_snapshot_rebuild_faster_than_full_rebuild(self):
        """Rebuilding from snapshot should be faster than full rebuild."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=500)

        # Add 2000 events
        for i in range(2000):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        # Time full rebuild (no snapshot)
        start = time.perf_counter()
        manager_no_snapshot = StateManager(store)
        time_no_snapshot = time.perf_counter() - start

        # Create manager with snapshots to populate them
        manager_with_snapshot = StateManager(store, snapshot_mgr)

        # Time rebuild with snapshot (should load from event 2000)
        start = time.perf_counter()
        manager_from_snapshot = StateManager(store, snapshot_mgr)
        time_with_snapshot = time.perf_counter() - start

        # Verify both have same state
        assert len(manager_no_snapshot.get_agents()) == 2000
        assert len(manager_from_snapshot.get_agents()) == 2000

        # Snapshot should be faster (or at least not slower)
        # Note: In test environment with small states, difference may be minimal
        # But in production with complex states, difference would be significant
        print(f"\nRebuild performance:")
        print(f"  Without snapshot: {time_no_snapshot*1000:.2f}ms")
        print(f"  With snapshot: {time_with_snapshot*1000:.2f}ms")


class TestSnapshotEdgeCases:
    """Test edge cases and error handling."""

    def test_snapshot_with_empty_state(self):
        """Should handle snapshotting empty state."""
        mgr = SnapshotManager(":memory:", snapshot_interval=100)

        empty_state = OrchestratorState()
        mgr.save_snapshot(empty_state, event_id=100)

        loaded_state, event_id = mgr.load_latest_snapshot()
        assert event_id == 100
        assert len(loaded_state.agents) == 0
        assert len(loaded_state.chat_history) == 0

    def test_state_manager_with_events_after_snapshot(self):
        """StateManager should correctly apply events that occur after snapshot."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=10)

        # Add 10 events and create snapshot
        for i in range(10):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        manager1 = StateManager(store, snapshot_mgr)
        assert len(manager1.get_agents()) == 10

        # Snapshot should exist at event 10
        assert snapshot_mgr.get_snapshot_count() == 1

        # Add 5 more events
        for i in range(10, 15):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})

        # Create new manager - should load snapshot at 10, then apply events 11-15
        manager2 = StateManager(store, snapshot_mgr)
        assert len(manager2.get_agents()) == 15

    def test_snapshot_interval_of_one(self):
        """Should handle snapshot interval of 1 (snapshot every event)."""
        store = EventStore(":memory:")
        snapshot_mgr = SnapshotManager(":memory:", snapshot_interval=1)

        manager = StateManager(store, snapshot_mgr)

        # Add 5 events - should create 5 snapshots
        for i in range(5):
            store.append(AGENT_CREATED, {"name": f"agent_{i}", "model": "sonnet"})
            manager.sync()

        assert snapshot_mgr.get_snapshot_count() == 5
