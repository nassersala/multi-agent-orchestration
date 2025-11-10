"""
Tests for EventStore - SQLite event log implementation.

These tests verify the core functionality of the event store including:
- Database and table creation
- Event appending with auto-incrementing IDs
- Event retrieval (all events, by type, by aggregate, since ID)
- JSON serialization round-trips
- Timestamp population
"""

import pytest
import tempfile
import os
import time
from pathlib import Path

from backend.event_store import EventStore


@pytest.fixture
def temp_db():
    """Create a temporary database file and clean it up after test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def event_store(temp_db):
    """Create an EventStore instance with temporary database."""
    return EventStore(temp_db)


@pytest.fixture
def memory_store():
    """Create an in-memory EventStore for faster tests."""
    return EventStore(":memory:")


class TestEventStoreBasics:
    """Test basic event store operations."""

    def test_database_and_table_creation(self, temp_db):
        """Test that database and events table are created."""
        # Create event store
        store = EventStore(temp_db)

        # Verify database file exists
        assert os.path.exists(temp_db)

        # Verify we can query the events table
        events = store.get_all()
        assert events == []

    def test_append_returns_auto_incrementing_id(self, memory_store):
        """Test that append returns auto-incrementing event IDs."""
        # Append first event
        id1 = memory_store.append(
            "TEST_EVENT",
            {"value": 1}
        )
        assert id1 == 1

        # Append second event
        id2 = memory_store.append(
            "TEST_EVENT",
            {"value": 2}
        )
        assert id2 == 2

        # Append third event
        id3 = memory_store.append(
            "TEST_EVENT",
            {"value": 3}
        )
        assert id3 == 3

    def test_append_with_all_optional_fields(self, memory_store):
        """Test appending event with all optional fields populated."""
        event_id = memory_store.append(
            event_type="AGENT_CREATED",
            data={"name": "alice", "model": "sonnet"},
            aggregate_id="agent_123",
            aggregate_type="agent",
            metadata={"user_id": "user_456", "ip": "127.0.0.1"}
        )

        assert event_id == 1

        # Retrieve and verify
        events = memory_store.get_all()
        assert len(events) == 1

        event = events[0]
        assert event['type'] == "AGENT_CREATED"
        assert event['aggregate_id'] == "agent_123"
        assert event['aggregate_type'] == "agent"
        assert event['data'] == {"name": "alice", "model": "sonnet"}
        assert event['metadata'] == {"user_id": "user_456", "ip": "127.0.0.1"}

    def test_retrieve_all_events(self, memory_store):
        """Test retrieving all events in order."""
        # Append multiple events
        memory_store.append("EVENT_1", {"value": 1})
        memory_store.append("EVENT_2", {"value": 2})
        memory_store.append("EVENT_3", {"value": 3})

        # Retrieve all
        events = memory_store.get_all()

        assert len(events) == 3
        assert events[0]['type'] == "EVENT_1"
        assert events[0]['data']['value'] == 1
        assert events[1]['type'] == "EVENT_2"
        assert events[1]['data']['value'] == 2
        assert events[2]['type'] == "EVENT_3"
        assert events[2]['data']['value'] == 3

    def test_json_serialization_round_trip(self, memory_store):
        """Test that complex JSON data serializes and deserializes correctly."""
        complex_data = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {
                "key": "value",
                "list": ["a", "b", "c"]
            }
        }

        # Append event with complex data
        memory_store.append("COMPLEX_EVENT", complex_data)

        # Retrieve and verify
        events = memory_store.get_all()
        assert len(events) == 1
        assert events[0]['data'] == complex_data

    def test_timestamps_populated_correctly(self, memory_store):
        """Test that timestamps are automatically populated."""
        # Record time before append
        before = time.time()

        # Append event
        memory_store.append("TIMED_EVENT", {"value": 1})

        # Small delay
        time.sleep(0.01)

        # Record time after
        after = time.time()

        # Retrieve event
        events = memory_store.get_all()
        assert len(events) == 1

        timestamp = events[0]['timestamp']
        assert before <= timestamp <= after


class TestEventStoreQueries:
    """Test event store query capabilities."""

    def test_since_returns_events_after_id(self, memory_store):
        """Test that since() returns only events with ID greater than specified."""
        # Append 5 events
        for i in range(1, 6):
            memory_store.append(f"EVENT_{i}", {"value": i})

        # Query events since id=2
        events = memory_store.since(2)

        assert len(events) == 3
        assert events[0]['id'] == 3
        assert events[1]['id'] == 4
        assert events[2]['id'] == 5

    def test_since_with_limit_parameter(self, memory_store):
        """Test that since() respects the limit parameter."""
        # Append 10 events
        for i in range(1, 11):
            memory_store.append(f"EVENT_{i}", {"value": i})

        # Query events since id=0 with limit=3
        events = memory_store.since(0, limit=3)

        assert len(events) == 3
        assert events[0]['id'] == 1
        assert events[1]['id'] == 2
        assert events[2]['id'] == 3

    def test_since_with_no_new_events(self, memory_store):
        """Test that since() returns empty list when no new events."""
        # Append 3 events
        for i in range(1, 4):
            memory_store.append(f"EVENT_{i}", {"value": i})

        # Query events since latest id
        events = memory_store.since(3)

        assert events == []

    def test_by_aggregate_filters_correctly(self, memory_store):
        """Test that by_aggregate() filters events by aggregate_id."""
        # Append events for different aggregates
        memory_store.append(
            "EVENT_1",
            {"value": 1},
            aggregate_id="agent_1",
            aggregate_type="agent"
        )
        memory_store.append(
            "EVENT_2",
            {"value": 2},
            aggregate_id="agent_2",
            aggregate_type="agent"
        )
        memory_store.append(
            "EVENT_3",
            {"value": 3},
            aggregate_id="agent_1",
            aggregate_type="agent"
        )
        memory_store.append(
            "EVENT_4",
            {"value": 4},
            aggregate_id="orchestrator_1",
            aggregate_type="orchestrator"
        )

        # Query events for agent_1
        events = memory_store.by_aggregate("agent_1")

        assert len(events) == 2
        assert events[0]['aggregate_id'] == "agent_1"
        assert events[0]['data']['value'] == 1
        assert events[1]['aggregate_id'] == "agent_1"
        assert events[1]['data']['value'] == 3

    def test_by_type_filters_correctly(self, memory_store):
        """Test that by_type() filters events by event type."""
        # Append events of different types
        memory_store.append("AGENT_CREATED", {"name": "alice"})
        memory_store.append("COST_INCURRED", {"cost": 0.01})
        memory_store.append("AGENT_CREATED", {"name": "bob"})
        memory_store.append("USER_MESSAGE", {"text": "hello"})
        memory_store.append("COST_INCURRED", {"cost": 0.02})

        # Query AGENT_CREATED events
        agent_events = memory_store.by_type("AGENT_CREATED")
        assert len(agent_events) == 2
        assert agent_events[0]['data']['name'] == "alice"
        assert agent_events[1]['data']['name'] == "bob"

        # Query COST_INCURRED events
        cost_events = memory_store.by_type("COST_INCURRED")
        assert len(cost_events) == 2
        assert cost_events[0]['data']['cost'] == 0.01
        assert cost_events[1]['data']['cost'] == 0.02


class TestEventStoreEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_store_returns_empty_list(self, memory_store):
        """Test that querying empty store returns empty list."""
        assert memory_store.get_all() == []
        assert memory_store.since(0) == []
        assert memory_store.by_type("ANY_TYPE") == []
        assert memory_store.by_aggregate("any_id") == []

    def test_metadata_can_be_none(self, memory_store):
        """Test that metadata can be None."""
        memory_store.append("TEST_EVENT", {"value": 1}, metadata=None)

        events = memory_store.get_all()
        assert events[0]['metadata'] is None

    def test_aggregate_fields_can_be_none(self, memory_store):
        """Test that aggregate_id and aggregate_type can be None."""
        memory_store.append(
            "TEST_EVENT",
            {"value": 1},
            aggregate_id=None,
            aggregate_type=None
        )

        events = memory_store.get_all()
        assert events[0]['aggregate_id'] is None
        assert events[0]['aggregate_type'] is None

    def test_version_defaults_to_1(self, memory_store):
        """Test that version field defaults to 1."""
        memory_store.append("TEST_EVENT", {"value": 1})

        events = memory_store.get_all()
        assert events[0]['version'] == 1


class TestEventStoreThreadSafety:
    """Test thread safety of event store operations."""

    def test_concurrent_appends(self, memory_store):
        """Test that concurrent appends work correctly."""
        import threading

        num_threads = 10
        events_per_thread = 10

        def append_events(thread_id):
            for i in range(events_per_thread):
                memory_store.append(
                    "CONCURRENT_EVENT",
                    {"thread_id": thread_id, "count": i}
                )

        # Create and start threads
        threads = []
        for thread_id in range(num_threads):
            t = threading.Thread(target=append_events, args=(thread_id,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Verify all events were written
        events = memory_store.get_all()
        assert len(events) == num_threads * events_per_thread

    def test_concurrent_reads_while_writing(self, memory_store):
        """Test that reads work correctly while writes are happening."""
        import threading

        stop_flag = threading.Event()
        read_count = [0]

        def write_events():
            for i in range(100):
                memory_store.append("WRITE_EVENT", {"count": i})
                time.sleep(0.001)

        def read_events():
            while not stop_flag.is_set():
                memory_store.get_all()
                read_count[0] += 1
                time.sleep(0.001)

        # Start writer thread
        writer = threading.Thread(target=write_events)
        writer.start()

        # Start reader threads
        readers = []
        for _ in range(3):
            t = threading.Thread(target=read_events)
            readers.append(t)
            t.start()

        # Wait for writer to finish
        writer.join()

        # Stop readers
        stop_flag.set()
        for t in readers:
            t.join()

        # Verify all events were written
        events = memory_store.get_all()
        assert len(events) == 100
        assert read_count[0] > 0  # Readers did some work
