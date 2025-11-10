"""
Tests for FastAPI basic endpoints.

This module tests the HTTP API layer including health checks,
state queries, and agent endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil

from backend.main import app
from backend.event_store import EventStore
from backend.event_types import (
    ORCHESTRATOR_INITIALIZED,
    AGENT_CREATED,
    AGENT_STATUS_CHANGED,
    COST_INCURRED,
    USER_MESSAGE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test databases."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def client(temp_dir):
    """
    Create a FastAPI test client with isolated database.

    Uses a temporary directory for event and snapshot databases
    to ensure test isolation.
    """
    # Override the data path in the app
    original_lifespan = app.router.lifespan_context

    # Create a new lifespan that uses temp directory
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def test_lifespan(app_instance):
        db_path = Path(temp_dir) / "events.db"
        snapshot_path = Path(temp_dir) / "snapshots.db"

        app_instance.state.event_store = EventStore(str(db_path))
        from backend.snapshot_manager import SnapshotManager
        app_instance.state.snapshot_manager = SnapshotManager(
            db_path=str(snapshot_path),
            snapshot_interval=1000
        )
        from backend.state_manager import StateManager
        app_instance.state.state_manager = StateManager(
            event_store=app_instance.state.event_store,
            snapshot_manager=app_instance.state.snapshot_manager
        )

        # Initial sync
        app_instance.state.state_manager.sync()
        yield

    app.router.lifespan_context = test_lifespan

    with TestClient(app) as client:
        yield client

    # Restore original lifespan
    app.router.lifespan_context = original_lifespan


def test_health_endpoint(client):
    """Test the /health endpoint returns correct status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
    assert "event_count" in data
    assert data["event_count"] >= 0


def test_health_endpoint_with_events(client):
    """Test /health endpoint reflects event count."""
    # Add some events directly to the event store
    event_store = client.app.state.event_store

    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-123",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-123"}
    )

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["event_count"] == 1


def test_get_state_empty(client):
    """Test /state endpoint with no events."""
    response = client.get("/state")

    assert response.status_code == 200
    data = response.json()

    assert data["orchestrator_id"] is None
    assert data["total_cost"] == 0.0
    assert data["total_input_tokens"] == 0
    assert data["total_output_tokens"] == 0
    assert data["agents_count"] == 0


def test_get_state_with_data(client):
    """Test /state endpoint with orchestrator data."""
    event_store = client.app.state.event_store

    # Initialize orchestrator
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-456",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-456"}
    )

    # Add an agent
    event_store.append(
        event_type=AGENT_CREATED,
        aggregate_id="orch-456",
        aggregate_type="orchestrator",
        data={
            "name": "alice",
            "system_prompt": "You are Alice",
            "model": "claude-sonnet-4",
        }
    )

    # Add cost
    event_store.append(
        event_type=COST_INCURRED,
        aggregate_id="orch-456",
        aggregate_type="orchestrator",
        data={
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": 0.001
        }
    )

    response = client.get("/state")
    assert response.status_code == 200
    data = response.json()

    assert data["orchestrator_id"] == "orch-456"
    assert data["total_cost"] == 0.001
    assert data["total_input_tokens"] == 100
    assert data["total_output_tokens"] == 50
    assert data["agents_count"] == 1


def test_get_agents_empty(client):
    """Test /agents endpoint with no agents."""
    response = client.get("/agents")

    assert response.status_code == 200
    data = response.json()

    assert data == {}


def test_get_agents_with_agents(client):
    """Test /agents endpoint returns all agents."""
    event_store = client.app.state.event_store

    # Initialize orchestrator
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-789",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-789"}
    )

    # Create two agents
    event_store.append(
        event_type=AGENT_CREATED,
        aggregate_id="orch-789",
        aggregate_type="orchestrator",
        data={
            "name": "alice",
            "system_prompt": "You are Alice",
            "model": "claude-sonnet-4",
        }
    )

    event_store.append(
        event_type=AGENT_CREATED,
        aggregate_id="orch-789",
        aggregate_type="orchestrator",
        data={
            "name": "bob",
            "system_prompt": "You are Bob",
            "model": "claude-opus-4",
        }
    )

    response = client.get("/agents")
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    assert "alice" in data
    assert "bob" in data

    alice = data["alice"]
    assert alice["name"] == "alice"
    assert alice["system_prompt"] == "You are Alice"
    assert alice["model"] == "claude-sonnet-4"
    assert alice["status"] == "idle"

    bob = data["bob"]
    assert bob["name"] == "bob"
    assert bob["system_prompt"] == "You are Bob"
    assert bob["model"] == "claude-opus-4"


def test_get_agent_by_name(client):
    """Test /agents/{name} endpoint returns specific agent."""
    event_store = client.app.state.event_store

    # Initialize and create agent
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-111",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-111"}
    )

    event_store.append(
        event_type=AGENT_CREATED,
        aggregate_id="orch-111",
        aggregate_type="orchestrator",
        data={
            "name": "charlie",
            "system_prompt": "You are Charlie",
            "model": "claude-haiku-4",
        }
    )

    response = client.get("/agents/charlie")
    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "charlie"
    assert data["system_prompt"] == "You are Charlie"
    assert data["model"] == "claude-haiku-4"
    assert data["status"] == "idle"


def test_get_agent_not_found(client):
    """Test /agents/{name} returns 404 for nonexistent agent."""
    response = client.get("/agents/nonexistent")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_get_chat_empty(client):
    """Test /chat endpoint with no messages."""
    response = client.get("/chat")

    assert response.status_code == 200
    data = response.json()

    assert data == []


def test_get_chat_with_messages(client):
    """Test /chat endpoint returns chat history."""
    event_store = client.app.state.event_store

    # Initialize orchestrator
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-222",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-222"}
    )

    # Add user message
    event_store.append(
        event_type=USER_MESSAGE_RECEIVED,
        aggregate_id="orch-222",
        aggregate_type="orchestrator",
        data={"message": "Hello!"}
    )

    # Add orchestrator response
    event_store.append(
        event_type=ORCHESTRATOR_RESPONSE_GENERATED,
        aggregate_id="orch-222",
        aggregate_type="orchestrator",
        data={"message": "Hi there!"}
    )

    response = client.get("/chat")
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    # Messages should be in order (most recent first in state)
    assert data[0]["sender"] == "user"
    assert data[0]["receiver"] == "orchestrator"
    assert data[0]["message"] == "Hello!"
    assert data[1]["sender"] == "orchestrator"
    assert data[1]["receiver"] == "user"
    assert data[1]["message"] == "Hi there!"


def test_get_chat_with_limit(client):
    """Test /chat endpoint respects limit parameter."""
    event_store = client.app.state.event_store

    # Initialize orchestrator
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-333",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-333"}
    )

    # Add 5 messages
    for i in range(5):
        event_store.append(
            event_type=USER_MESSAGE_RECEIVED,
            aggregate_id="orch-333",
            aggregate_type="orchestrator",
            data={"message": f"Message {i}"}
        )

    # Request only 2 messages
    response = client.get("/chat?limit=2")
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2


def test_get_chat_limit_validation(client):
    """Test /chat endpoint validates limit parameter."""
    # Limit too small
    response = client.get("/chat?limit=0")
    assert response.status_code == 422  # Validation error

    # Limit too large
    response = client.get("/chat?limit=2000")
    assert response.status_code == 422  # Validation error

    # Valid limits
    response = client.get("/chat?limit=1")
    assert response.status_code == 200

    response = client.get("/chat?limit=1000")
    assert response.status_code == 200


def test_get_cost_empty(client):
    """Test /cost endpoint with no events."""
    response = client.get("/cost")

    assert response.status_code == 200
    data = response.json()

    assert data["total_cost"] == 0.0
    assert data["total_input_tokens"] == 0
    assert data["total_output_tokens"] == 0
    assert data["event_count"] == 0


def test_get_cost_with_usage(client):
    """Test /cost endpoint with cost data."""
    event_store = client.app.state.event_store

    # Initialize orchestrator
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-444",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-444"}
    )

    # Add multiple cost events
    event_store.append(
        event_type=COST_INCURRED,
        aggregate_id="orch-444",
        aggregate_type="orchestrator",
        data={
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": 0.001
        }
    )

    event_store.append(
        event_type=COST_INCURRED,
        aggregate_id="orch-444",
        aggregate_type="orchestrator",
        data={
            "input_tokens": 200,
            "output_tokens": 100,
            "cost": 0.002
        }
    )

    response = client.get("/cost")
    assert response.status_code == 200
    data = response.json()

    assert data["total_cost"] == 0.003
    assert data["total_input_tokens"] == 300
    assert data["total_output_tokens"] == 150
    assert data["event_count"] == 3  # INIT + 2 COST events


def test_state_sync_across_endpoints(client):
    """Test that state syncs correctly across multiple endpoint calls."""
    event_store = client.app.state.event_store

    # Initialize
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-sync",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-sync"}
    )

    # First call to /state
    response1 = client.get("/state")
    assert response1.json()["agents_count"] == 0

    # Add agent
    event_store.append(
        event_type=AGENT_CREATED,
        aggregate_id="orch-sync",
        aggregate_type="orchestrator",
        data={
            "name": "synced-agent",
            "system_prompt": "Sync test",
            "model": "claude-sonnet-4",
        }
    )

    # Second call to /state should see the new agent
    response2 = client.get("/state")
    assert response2.json()["agents_count"] == 1

    # /agents endpoint should also see it
    response3 = client.get("/agents")
    assert "synced-agent" in response3.json()


def test_agent_status_change(client):
    """Test that agent status changes are reflected in API."""
    event_store = client.app.state.event_store

    # Initialize and create agent
    event_store.append(
        event_type=ORCHESTRATOR_INITIALIZED,
        aggregate_id="orch-status",
        aggregate_type="orchestrator",
        data={"orchestrator_id": "orch-status"}
    )

    event_store.append(
        event_type=AGENT_CREATED,
        aggregate_id="orch-status",
        aggregate_type="orchestrator",
        data={
            "name": "status-agent",
            "system_prompt": "Status test",
            "model": "claude-sonnet-4",
        }
    )

    # Check initial status
    response1 = client.get("/agents/status-agent")
    assert response1.json()["status"] == "idle"

    # Change status to running
    event_store.append(
        event_type=AGENT_STATUS_CHANGED,
        aggregate_id="status-agent",
        aggregate_type="agent",
        data={"agent_name": "status-agent", "new_status": "running"}
    )

    # Check updated status
    response2 = client.get("/agents/status-agent")
    assert response2.json()["status"] == "running"


def test_cors_middleware_configured(client):
    """Test that CORS middleware is configured."""
    # In production, CORS headers would be present, but TestClient doesn't
    # include middleware headers. We just verify the endpoint works.
    response = client.get("/health")
    assert response.status_code == 200

    # Verify the app has CORS middleware by checking the middleware stack
    # This is a simple smoke test to ensure CORS is configured
    assert any("CORSMiddleware" in str(m) for m in client.app.user_middleware)
