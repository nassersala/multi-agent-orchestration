"""
FastAPI server for event-sourced multi-agent orchestration system.

This module provides the HTTP API layer for the orchestration system,
including state queries, command endpoints, and SSE streaming.
"""

from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.event_store import EventStore
from backend.snapshot_manager import SnapshotManager
from backend.state_manager import StateManager
from backend.models import Agent, ChatMessage, OrchestratorState


# Pydantic models for API responses
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    event_count: int


class StateResponse(BaseModel):
    """Current orchestrator state response."""
    orchestrator_id: Optional[str]
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    agents_count: int


class AgentResponse(BaseModel):
    """Agent information response."""
    name: str
    system_prompt: str
    model: str
    status: str
    session_id: Optional[str] = None
    working_dir: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0


class ChatMessageResponse(BaseModel):
    """Chat message response."""
    sender: str
    receiver: str
    message: str
    timestamp: str  # ISO format datetime
    agent_name: Optional[str] = None


class CostSummary(BaseModel):
    """Cost summary response."""
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    event_count: int


# Application state
class AppState:
    """Application state container."""
    event_store: EventStore
    snapshot_manager: SnapshotManager
    state_manager: StateManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Initializes and cleans up application resources.
    """
    # Startup: Initialize event store and state manager
    db_path = Path("data/events.db")
    db_path.parent.mkdir(exist_ok=True)

    app.state.event_store = EventStore(str(db_path))
    app.state.snapshot_manager = SnapshotManager(
        db_path=str(db_path.parent / "snapshots.db"),
        snapshot_interval=1000
    )
    app.state.state_manager = StateManager(
        event_store=app.state.event_store,
        snapshot_manager=app.state.snapshot_manager
    )

    # Initial sync
    app.state.state_manager.sync()

    yield

    # Shutdown: Cleanup (SQLite connections auto-close)
    pass


# Create FastAPI app
app = FastAPI(
    title="Multi-Agent Orchestration API",
    description="Event-sourced multi-agent orchestration system with SSE streaming",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health endpoint
@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Health check endpoint.

    Returns service status and basic metrics.
    """
    # Sync state before returning health info
    app.state.state_manager.sync()

    # Get event count from event store
    all_events = app.state.event_store.get_all()

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        event_count=len(all_events)
    )


# State endpoint
@app.get("/state", response_model=StateResponse)
async def get_state():
    """
    Get current orchestrator state.

    Returns aggregated state information including cost and agent count.
    """
    # Sync to get latest state
    app.state.state_manager.sync()

    state = app.state.state_manager.get_state()
    agents = app.state.state_manager.get_agents()

    return StateResponse(
        orchestrator_id=state.orchestrator_id,
        total_cost=state.total_cost,
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        agents_count=len(agents)
    )


# Agents list endpoint
@app.get("/agents", response_model=Dict[str, AgentResponse])
async def get_agents():
    """
    Get all agents.

    Returns a dictionary of all agents indexed by name.
    """
    # Sync to get latest state
    app.state.state_manager.sync()

    agents = app.state.state_manager.get_agents()

    # Convert Agent dataclasses to AgentResponse models
    return {
        name: AgentResponse(
            name=agent.name,
            system_prompt=agent.system_prompt,
            model=agent.model,
            status=agent.status,
            session_id=agent.session_id,
            working_dir=agent.working_dir,
            input_tokens=agent.input_tokens,
            output_tokens=agent.output_tokens,
            total_cost=agent.total_cost
        )
        for name, agent in agents.items()
    }


# Single agent endpoint
@app.get("/agents/{name}", response_model=AgentResponse)
async def get_agent(name: str):
    """
    Get a specific agent by name.

    Args:
        name: Agent name

    Returns:
        Agent information

    Raises:
        HTTPException: 404 if agent not found
    """
    # Sync to get latest state
    app.state.state_manager.sync()

    agent = app.state.state_manager.get_agent(name)

    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    return AgentResponse(
        name=agent.name,
        system_prompt=agent.system_prompt,
        model=agent.model,
        status=agent.status,
        session_id=agent.session_id,
        working_dir=agent.working_dir,
        input_tokens=agent.input_tokens,
        output_tokens=agent.output_tokens,
        total_cost=agent.total_cost
    )


# Chat history endpoint
@app.get("/chat", response_model=List[ChatMessageResponse])
async def get_chat(limit: int = Query(default=100, ge=1, le=1000)):
    """
    Get chat history.

    Args:
        limit: Maximum number of messages to return (1-1000)

    Returns:
        List of chat messages, most recent first
    """
    # Sync to get latest state
    app.state.state_manager.sync()

    messages = app.state.state_manager.get_chat_history(limit=limit)

    return [
        ChatMessageResponse(
            sender=msg.sender,
            receiver=msg.receiver,
            message=msg.message,
            timestamp=msg.timestamp.isoformat() if isinstance(msg.timestamp, datetime) else msg.timestamp,
            agent_name=msg.agent_name
        )
        for msg in messages
    ]


# Cost summary endpoint
@app.get("/cost", response_model=CostSummary)
async def get_cost():
    """
    Get cost summary.

    Returns total cost and token usage across all operations.
    """
    # Sync to get latest state
    app.state.state_manager.sync()

    state = app.state.state_manager.get_state()
    all_events = app.state.event_store.get_all()

    return CostSummary(
        total_cost=state.total_cost,
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        event_count=len(all_events)
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
