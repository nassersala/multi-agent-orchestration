"""
Immutable data models for event sourcing state.

All models are frozen dataclasses to ensure immutability.
State transitions create new instances rather than mutating existing ones.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal
from datetime import datetime


# ═══════════════════════════════════════════════════════════
# STATUS TYPES
# ═══════════════════════════════════════════════════════════

AgentStatus = Literal['idle', 'executing', 'waiting', 'blocked', 'complete']
SenderType = Literal['user', 'orchestrator', 'agent']


# ═══════════════════════════════════════════════════════════
# AGENT MODEL
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Agent:
    """
    Immutable agent configuration and state.

    Represents a managed agent created by the orchestrator.
    All state changes produce new Agent instances.
    """
    name: str
    model: str
    system_prompt: str = ""
    status: AgentStatus = 'idle'
    session_id: Optional[str] = None
    working_dir: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    metadata: Dict[str, any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def with_status(self, status: AgentStatus) -> 'Agent':
        """Return new Agent with updated status."""
        from dataclasses import replace
        return replace(self, status=status)

    def with_cost(self, input_tokens: int, output_tokens: int, cost: float) -> 'Agent':
        """Return new Agent with updated cost metrics."""
        from dataclasses import replace
        return replace(
            self,
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
            total_cost=self.total_cost + cost
        )


# ═══════════════════════════════════════════════════════════
# CHAT MESSAGE MODEL
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ChatMessage:
    """
    Immutable chat message in the conversation history.

    Represents messages between user, orchestrator, and agents.
    """
    sender: SenderType
    receiver: SenderType
    message: str
    timestamp: datetime
    agent_name: Optional[str] = None
    metadata: Dict[str, any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# ORCHESTRATOR STATE MODEL
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OrchestratorState:
    """
    Complete immutable state of the orchestration system.

    This is the projection of all events in the event log.
    Every state transition creates a new OrchestratorState instance.
    """
    orchestrator_id: Optional[str] = None
    session_id: Optional[str] = None
    status: AgentStatus = 'idle'
    agents: Dict[str, Agent] = field(default_factory=dict)
    chat_history: List[ChatMessage] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    metadata: Dict[str, any] = field(default_factory=dict)
    last_updated: Optional[datetime] = None

    def with_agent(self, agent: Agent) -> 'OrchestratorState':
        """Return new state with agent added or updated."""
        from dataclasses import replace
        new_agents = {**self.agents, agent.name: agent}
        return replace(self, agents=new_agents, last_updated=datetime.utcnow())

    def without_agent(self, agent_name: str) -> 'OrchestratorState':
        """Return new state with agent removed."""
        from dataclasses import replace
        new_agents = {k: v for k, v in self.agents.items() if k != agent_name}
        return replace(self, agents=new_agents, last_updated=datetime.utcnow())

    def with_message(self, message: ChatMessage) -> 'OrchestratorState':
        """Return new state with chat message appended."""
        from dataclasses import replace
        new_history = [*self.chat_history, message]
        return replace(self, chat_history=new_history, last_updated=datetime.utcnow())

    def with_cost(self, input_tokens: int, output_tokens: int, cost: float) -> 'OrchestratorState':
        """Return new state with updated cost totals."""
        from dataclasses import replace
        return replace(
            self,
            total_input_tokens=self.total_input_tokens + input_tokens,
            total_output_tokens=self.total_output_tokens + output_tokens,
            total_cost=self.total_cost + cost,
            last_updated=datetime.utcnow()
        )

    def with_status(self, status: AgentStatus) -> 'OrchestratorState':
        """Return new state with updated orchestrator status."""
        from dataclasses import replace
        return replace(self, status=status, last_updated=datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "Agent",
    "ChatMessage",
    "OrchestratorState",
    "AgentStatus",
    "SenderType",
]
