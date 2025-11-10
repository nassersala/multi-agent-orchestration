"""
Tests for immutable data models.

Verifies that all models are truly immutable and behave correctly.
"""

import pytest
from datetime import datetime
from dataclasses import FrozenInstanceError

from backend.models import Agent, ChatMessage, OrchestratorState


# ═══════════════════════════════════════════════════════════
# AGENT MODEL TESTS
# ═══════════════════════════════════════════════════════════

def test_agent_is_immutable():
    """Agent dataclass should be frozen (immutable)."""
    agent = Agent(name="alice", model="sonnet")

    with pytest.raises(FrozenInstanceError):
        agent.status = 'executing'  # type: ignore


def test_agent_default_values():
    """Agent should have sensible defaults."""
    agent = Agent(name="alice", model="sonnet")

    assert agent.name == "alice"
    assert agent.model == "sonnet"
    assert agent.system_prompt == ""
    assert agent.status == 'idle'
    assert agent.session_id is None
    assert agent.working_dir is None
    assert agent.input_tokens == 0
    assert agent.output_tokens == 0
    assert agent.total_cost == 0.0
    assert agent.metadata == {}
    assert agent.created_at is None


def test_agent_with_all_fields():
    """Agent should accept all fields on creation."""
    now = datetime.utcnow()
    agent = Agent(
        name="bob",
        model="haiku",
        system_prompt="You are a helpful agent",
        status='executing',
        session_id="session_123",
        working_dir="/tmp/work",
        input_tokens=100,
        output_tokens=50,
        total_cost=0.05,
        metadata={"key": "value"},
        created_at=now
    )

    assert agent.name == "bob"
    assert agent.model == "haiku"
    assert agent.system_prompt == "You are a helpful agent"
    assert agent.status == 'executing'
    assert agent.session_id == "session_123"
    assert agent.working_dir == "/tmp/work"
    assert agent.input_tokens == 100
    assert agent.output_tokens == 50
    assert agent.total_cost == 0.05
    assert agent.metadata == {"key": "value"}
    assert agent.created_at == now


def test_agent_with_status_creates_new_instance():
    """Agent.with_status should create new instance, not mutate."""
    agent1 = Agent(name="alice", model="sonnet", status='idle')
    agent2 = agent1.with_status('executing')

    # Original unchanged
    assert agent1.status == 'idle'
    # New instance has updated status
    assert agent2.status == 'executing'
    # Different objects
    assert agent1 is not agent2
    # Other fields same
    assert agent2.name == agent1.name
    assert agent2.model == agent1.model


def test_agent_with_cost_creates_new_instance():
    """Agent.with_cost should create new instance with accumulated costs."""
    agent1 = Agent(
        name="alice",
        model="sonnet",
        input_tokens=100,
        output_tokens=50,
        total_cost=0.05
    )
    agent2 = agent1.with_cost(input_tokens=200, output_tokens=100, cost=0.10)

    # Original unchanged
    assert agent1.input_tokens == 100
    assert agent1.output_tokens == 50
    assert agent1.total_cost == 0.05

    # New instance has accumulated costs
    assert agent2.input_tokens == 300
    assert agent2.output_tokens == 150
    assert agent2.total_cost == pytest.approx(0.15)

    # Different objects
    assert agent1 is not agent2


# ═══════════════════════════════════════════════════════════
# CHAT MESSAGE MODEL TESTS
# ═══════════════════════════════════════════════════════════

def test_chat_message_is_immutable():
    """ChatMessage dataclass should be frozen."""
    now = datetime.utcnow()
    msg = ChatMessage(
        sender='user',
        receiver='orchestrator',
        message="Hello",
        timestamp=now
    )

    with pytest.raises(FrozenInstanceError):
        msg.message = "Changed"  # type: ignore


def test_chat_message_default_values():
    """ChatMessage should have sensible defaults."""
    now = datetime.utcnow()
    msg = ChatMessage(
        sender='user',
        receiver='orchestrator',
        message="Hello",
        timestamp=now
    )

    assert msg.sender == 'user'
    assert msg.receiver == 'orchestrator'
    assert msg.message == "Hello"
    assert msg.timestamp == now
    assert msg.agent_name is None
    assert msg.metadata == {}


def test_chat_message_with_all_fields():
    """ChatMessage should accept all fields."""
    now = datetime.utcnow()
    msg = ChatMessage(
        sender='agent',
        receiver='orchestrator',
        message="Task complete",
        timestamp=now,
        agent_name="alice",
        metadata={"task_id": "123"}
    )

    assert msg.sender == 'agent'
    assert msg.receiver == 'orchestrator'
    assert msg.message == "Task complete"
    assert msg.timestamp == now
    assert msg.agent_name == "alice"
    assert msg.metadata == {"task_id": "123"}


# ═══════════════════════════════════════════════════════════
# ORCHESTRATOR STATE MODEL TESTS
# ═══════════════════════════════════════════════════════════

def test_orchestrator_state_is_immutable():
    """OrchestratorState dataclass should be frozen."""
    state = OrchestratorState()

    with pytest.raises(FrozenInstanceError):
        state.status = 'executing'  # type: ignore


def test_orchestrator_state_default_values():
    """OrchestratorState should have sensible defaults."""
    state = OrchestratorState()

    assert state.orchestrator_id is None
    assert state.session_id is None
    assert state.status == 'idle'
    assert state.agents == {}
    assert state.chat_history == []
    assert state.total_input_tokens == 0
    assert state.total_output_tokens == 0
    assert state.total_cost == 0.0
    assert state.metadata == {}
    assert state.last_updated is None


def test_orchestrator_state_with_all_fields():
    """OrchestratorState should accept all fields."""
    now = datetime.utcnow()
    agent = Agent(name="alice", model="sonnet")
    msg = ChatMessage(
        sender='user',
        receiver='orchestrator',
        message="Hello",
        timestamp=now
    )

    state = OrchestratorState(
        orchestrator_id="orch_123",
        session_id="session_456",
        status='executing',
        agents={"alice": agent},
        chat_history=[msg],
        total_input_tokens=1000,
        total_output_tokens=500,
        total_cost=0.50,
        metadata={"version": "1.0"},
        last_updated=now
    )

    assert state.orchestrator_id == "orch_123"
    assert state.session_id == "session_456"
    assert state.status == 'executing'
    assert "alice" in state.agents
    assert len(state.chat_history) == 1
    assert state.total_input_tokens == 1000
    assert state.total_output_tokens == 500
    assert state.total_cost == 0.50
    assert state.metadata == {"version": "1.0"}
    assert state.last_updated == now


def test_orchestrator_state_with_agent_creates_new_instance():
    """OrchestratorState.with_agent should create new instance."""
    state1 = OrchestratorState()
    agent = Agent(name="alice", model="sonnet")
    state2 = state1.with_agent(agent)

    # Original unchanged
    assert state1.agents == {}
    # New instance has agent
    assert "alice" in state2.agents
    assert state2.agents["alice"] == agent
    # Different objects
    assert state1 is not state2
    # Last updated timestamp set
    assert state2.last_updated is not None


def test_orchestrator_state_with_agent_updates_existing():
    """OrchestratorState.with_agent should update existing agent."""
    agent1 = Agent(name="alice", model="sonnet", status='idle')
    state1 = OrchestratorState(agents={"alice": agent1})

    agent2 = agent1.with_status('executing')
    state2 = state1.with_agent(agent2)

    # Original agent unchanged
    assert state1.agents["alice"].status == 'idle'
    # New state has updated agent
    assert state2.agents["alice"].status == 'executing'


def test_orchestrator_state_without_agent_creates_new_instance():
    """OrchestratorState.without_agent should create new instance."""
    agent = Agent(name="alice", model="sonnet")
    state1 = OrchestratorState(agents={"alice": agent})
    state2 = state1.without_agent("alice")

    # Original unchanged
    assert "alice" in state1.agents
    # New instance has agent removed
    assert "alice" not in state2.agents
    # Different objects
    assert state1 is not state2


def test_orchestrator_state_with_message_creates_new_instance():
    """OrchestratorState.with_message should create new instance."""
    state1 = OrchestratorState()
    msg = ChatMessage(
        sender='user',
        receiver='orchestrator',
        message="Hello",
        timestamp=datetime.utcnow()
    )
    state2 = state1.with_message(msg)

    # Original unchanged
    assert len(state1.chat_history) == 0
    # New instance has message
    assert len(state2.chat_history) == 1
    assert state2.chat_history[0] == msg
    # Different objects
    assert state1 is not state2


def test_orchestrator_state_with_cost_creates_new_instance():
    """OrchestratorState.with_cost should create new instance with accumulated costs."""
    state1 = OrchestratorState(
        total_input_tokens=100,
        total_output_tokens=50,
        total_cost=0.05
    )
    state2 = state1.with_cost(input_tokens=200, output_tokens=100, cost=0.10)

    # Original unchanged
    assert state1.total_input_tokens == 100
    assert state1.total_output_tokens == 50
    assert state1.total_cost == 0.05

    # New instance has accumulated costs
    assert state2.total_input_tokens == 300
    assert state2.total_output_tokens == 150
    assert state2.total_cost == pytest.approx(0.15)

    # Different objects
    assert state1 is not state2


def test_orchestrator_state_with_status_creates_new_instance():
    """OrchestratorState.with_status should create new instance."""
    state1 = OrchestratorState(status='idle')
    state2 = state1.with_status('executing')

    # Original unchanged
    assert state1.status == 'idle'
    # New instance has updated status
    assert state2.status == 'executing'
    # Different objects
    assert state1 is not state2


def test_immutability_prevents_dict_mutation():
    """Verify that even nested dicts don't allow mutation via dataclass."""
    agent = Agent(name="alice", model="sonnet")
    state = OrchestratorState(agents={"alice": agent})

    # This should not mutate the dataclass itself
    # (though it would mutate the dict if we kept a reference)
    with pytest.raises(FrozenInstanceError):
        state.agents = {}  # type: ignore


def test_immutability_prevents_list_mutation():
    """Verify that even nested lists don't allow mutation via dataclass."""
    msg = ChatMessage(
        sender='user',
        receiver='orchestrator',
        message="Hello",
        timestamp=datetime.utcnow()
    )
    state = OrchestratorState(chat_history=[msg])

    # This should not mutate the dataclass itself
    with pytest.raises(FrozenInstanceError):
        state.chat_history = []  # type: ignore
