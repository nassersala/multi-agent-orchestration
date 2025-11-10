"""
Performance tests for event store.

These tests verify that the event store meets performance targets:
- Append: <1ms per event
- Query: <10ms for 1000 events
- Since: <10ms for incremental reads
"""

import pytest
import time
import tempfile
import os
from pathlib import Path
from backend.event_store import EventStore


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def event_store_with_data(temp_db):
    """Create event store with 1000 test events across 10 aggregates."""
    store = EventStore(temp_db)

    # Append 1000 events across 10 aggregates
    for i in range(1000):
        aggregate_id = f"aggregate_{i % 10}"
        event_type = f"EVENT_TYPE_{i % 5}"
        data = {
            "index": i,
            "message": f"Event {i}",
            "timestamp": time.time()
        }
        store.append(
            event_type=event_type,
            data=data,
            aggregate_id=aggregate_id,
            aggregate_type="test_aggregate"
        )

    return store


def test_append_performance(temp_db):
    """Test that append operations complete in <1ms on average."""
    store = EventStore(temp_db)

    num_events = 1000
    start_time = time.perf_counter()

    for i in range(num_events):
        store.append(
            event_type="PERFORMANCE_TEST",
            data={"index": i, "value": f"test_{i}"}
        )

    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time_ms = (total_time / num_events) * 1000

    print(f"\nAppend Performance:")
    print(f"  Total events: {num_events}")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  Average time per append: {avg_time_ms:.3f}ms")
    print(f"  Events per second: {num_events / total_time:.0f}")

    # Target: <1ms per append
    assert avg_time_ms < 1.0, f"Average append time {avg_time_ms:.3f}ms exceeds 1ms target"


def test_query_by_aggregate_performance(event_store_with_data):
    """Test that by_aggregate query completes in <10ms."""
    store = event_store_with_data

    # Query for one aggregate (should return 100 events)
    start_time = time.perf_counter()
    results = store.by_aggregate("aggregate_0")
    end_time = time.perf_counter()

    query_time_ms = (end_time - start_time) * 1000

    print(f"\nQuery by Aggregate Performance:")
    print(f"  Events returned: {len(results)}")
    print(f"  Query time: {query_time_ms:.3f}ms")

    # Verify correct number of results
    assert len(results) == 100, f"Expected 100 events, got {len(results)}"

    # Target: <10ms
    assert query_time_ms < 10.0, f"Query time {query_time_ms:.3f}ms exceeds 10ms target"


def test_query_by_type_performance(event_store_with_data):
    """Test that by_type query completes in <10ms."""
    store = event_store_with_data

    # Query for one event type (should return 200 events)
    start_time = time.perf_counter()
    results = store.by_type("EVENT_TYPE_0")
    end_time = time.perf_counter()

    query_time_ms = (end_time - start_time) * 1000

    print(f"\nQuery by Type Performance:")
    print(f"  Events returned: {len(results)}")
    print(f"  Query time: {query_time_ms:.3f}ms")

    # Verify correct number of results
    assert len(results) == 200, f"Expected 200 events, got {len(results)}"

    # Target: <10ms
    assert query_time_ms < 10.0, f"Query time {query_time_ms:.3f}ms exceeds 10ms target"


def test_since_performance(event_store_with_data):
    """Test that since query completes in <10ms."""
    store = event_store_with_data

    # Query events since ID 500 (should return 500 events)
    start_time = time.perf_counter()
    results = store.since(500)
    end_time = time.perf_counter()

    query_time_ms = (end_time - start_time) * 1000

    print(f"\nSince Query Performance:")
    print(f"  Events returned: {len(results)}")
    print(f"  Query time: {query_time_ms:.3f}ms")

    # Verify correct number of results
    assert len(results) == 500, f"Expected 500 events, got {len(results)}"

    # Target: <10ms
    assert query_time_ms < 10.0, f"Query time {query_time_ms:.3f}ms exceeds 10ms target"


def test_since_with_limit_performance(event_store_with_data):
    """Test that since with limit completes in <10ms."""
    store = event_store_with_data

    # Query with limit (should return 100 events)
    start_time = time.perf_counter()
    results = store.since(0, limit=100)
    end_time = time.perf_counter()

    query_time_ms = (end_time - start_time) * 1000

    print(f"\nSince with Limit Performance:")
    print(f"  Events returned: {len(results)}")
    print(f"  Query time: {query_time_ms:.3f}ms")

    # Verify correct number of results
    assert len(results) == 100, f"Expected 100 events, got {len(results)}"

    # Target: <10ms
    assert query_time_ms < 10.0, f"Query time {query_time_ms:.3f}ms exceeds 10ms target"


def test_get_all_performance(event_store_with_data):
    """Test that get_all query completes in reasonable time for 1000 events."""
    store = event_store_with_data

    # Get all events
    start_time = time.perf_counter()
    results = store.get_all()
    end_time = time.perf_counter()

    query_time_ms = (end_time - start_time) * 1000

    print(f"\nGet All Performance:")
    print(f"  Events returned: {len(results)}")
    print(f"  Query time: {query_time_ms:.3f}ms")

    # Verify correct number of results
    assert len(results) == 1000, f"Expected 1000 events, got {len(results)}"

    # Target: <50ms for getting all 1000 events
    assert query_time_ms < 50.0, f"Query time {query_time_ms:.3f}ms exceeds 50ms target"


def test_concurrent_read_performance(event_store_with_data):
    """Test that concurrent reads don't degrade performance significantly."""
    import threading

    store = event_store_with_data
    results = []
    errors = []

    def read_operation():
        try:
            start = time.perf_counter()
            events = store.by_aggregate("aggregate_0")
            elapsed = time.perf_counter() - start
            results.append((len(events), elapsed))
        except Exception as e:
            errors.append(e)

    # Create 10 concurrent readers
    threads = []
    for _ in range(10):
        t = threading.Thread(target=read_operation)
        threads.append(t)

    # Start all threads
    start_time = time.perf_counter()
    for t in threads:
        t.start()

    # Wait for all to complete
    for t in threads:
        t.join()

    total_time = time.perf_counter() - start_time

    print(f"\nConcurrent Read Performance:")
    print(f"  Threads: 10")
    print(f"  Total time: {total_time * 1000:.3f}ms")
    print(f"  Average per thread: {sum(r[1] for r in results) / len(results) * 1000:.3f}ms")

    # Verify no errors
    assert len(errors) == 0, f"Errors during concurrent reads: {errors}"

    # Verify all reads returned correct data
    assert all(count == 100 for count, _ in results), "Not all reads returned 100 events"

    # Target: Average time per thread should still be <10ms
    avg_time_ms = sum(r[1] for r in results) / len(results) * 1000
    assert avg_time_ms < 10.0, f"Average concurrent read time {avg_time_ms:.3f}ms exceeds 10ms target"


def test_write_read_performance(temp_db):
    """Test write-then-read performance (common pattern)."""
    store = EventStore(temp_db)

    num_iterations = 100
    times = []

    for i in range(num_iterations):
        # Write
        start = time.perf_counter()
        event_id = store.append(
            event_type="TEST_EVENT",
            data={"index": i}
        )

        # Immediate read
        events = store.since(event_id - 1, limit=1)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        # Verify we got our event back
        assert len(events) == 1
        assert events[0]["data"]["index"] == i

    avg_time_ms = (sum(times) / len(times)) * 1000

    print(f"\nWrite-then-Read Performance:")
    print(f"  Iterations: {num_iterations}")
    print(f"  Average time: {avg_time_ms:.3f}ms")

    # Target: <2ms for write + read cycle
    assert avg_time_ms < 2.0, f"Average write-read time {avg_time_ms:.3f}ms exceeds 2ms target"


if __name__ == "__main__":
    # Run with: pytest tests/test_event_store_performance.py -v -s
    pytest.main([__file__, "-v", "-s"])
