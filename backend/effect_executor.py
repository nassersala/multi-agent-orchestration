"""
Effect executor for executing side effects.

The EffectExecutor is responsible for:
1. Executing side effects produced by command handlers
2. Creating Claude SDK clients
3. Executing agent commands
4. Executing orchestrator responses
5. Logging all executions and errors as events

This separates side effects from pure command logic.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import traceback

from backend.event_store import EventStore
from backend.effects import Effect
from backend.event_types import (
    AGENT_STATUS_CHANGED,
    AGENT_RESPONSE_RECEIVED,
    ORCHESTRATOR_RESPONSE_GENERATED,
    EFFECT_EXECUTION_FAILED,
    COST_INCURRED,
)


class EffectExecutor:
    """
    Executes side effects and logs results as events.

    The EffectExecutor maintains state about running Claude clients
    and executes effects asynchronously. All executions are logged
    as events in the event store for auditing and debugging.

    Example:
        >>> store = EventStore(":memory:")
        >>> executor = EffectExecutor(store)
        >>> effects = [Effect(type="create_claude_client", data={...})]
        >>> await executor.execute(effects)
    """

    def __init__(self, event_store: EventStore):
        """
        Initialize effect executor.

        Args:
            event_store: EventStore to log execution events to
        """
        self._event_store = event_store
        self._claude_clients: Dict[str, Any] = {}

    async def execute(self, effects: List[Effect]) -> None:
        """
        Execute a list of effects in sequence.

        Effects are executed one at a time to maintain order.
        Errors are caught and logged as EFFECT_EXECUTION_FAILED events.

        Args:
            effects: List of Effect objects to execute
        """
        for effect in effects:
            try:
                await self._execute_one(effect)
            except Exception as e:
                # Log error as event
                self._event_store.append(
                    event_type=EFFECT_EXECUTION_FAILED,
                    data={
                        "effect_type": effect.type,
                        "effect_data": effect.data,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    metadata={"severity": "error"}
                )

    async def _execute_one(self, effect: Effect) -> None:
        """
        Execute a single effect.

        Dispatches to the appropriate handler based on effect type.

        Args:
            effect: Effect to execute

        Raises:
            ValueError: If effect type is unknown
        """
        if effect.type == "create_claude_client":
            await self._create_claude_client(effect.data)
        elif effect.type == "execute_agent_command":
            await self._execute_agent_command(effect.data)
        elif effect.type == "execute_orchestrator":
            await self._execute_orchestrator(effect.data)
        else:
            raise ValueError(f"Unknown effect type: {effect.type}")

    async def _create_claude_client(self, data: Dict[str, Any]) -> None:
        """
        Create a Claude SDK client for an agent.

        This is a mock implementation. Step 10 will integrate the real SDK.

        Args:
            data: Effect data containing:
                - agent_name: Name of agent
                - model: Claude model to use
                - system_prompt: System prompt for agent
                - template: Optional template name
        """
        agent_name = data["agent_name"]
        model = data["model"]

        # Mock: Store placeholder client
        self._claude_clients[agent_name] = {
            "model": model,
            "system_prompt": data["system_prompt"],
            "template": data.get("template"),
            "created_at": datetime.utcnow().isoformat(),
        }

        # Log agent status change
        self._event_store.append(
            event_type=AGENT_STATUS_CHANGED,
            data={
                "agent_name": agent_name,
                "old_status": "idle",
                "new_status": "idle",
                "reason": "client_created",
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_id=agent_name,
            aggregate_type="agent"
        )

    async def _execute_agent_command(self, data: Dict[str, Any]) -> None:
        """
        Execute a command on an agent.

        This is a mock implementation. Step 10 will integrate the real SDK.

        Args:
            data: Effect data containing:
                - agent_name: Name of agent to execute command on
                - command: Command/prompt to send to agent
        """
        agent_name = data["agent_name"]
        command = data["command"]

        # Mock: Simulate agent execution
        await asyncio.sleep(0.01)  # Simulate async work

        # Log status change to executing
        self._event_store.append(
            event_type=AGENT_STATUS_CHANGED,
            data={
                "agent_name": agent_name,
                "old_status": "idle",
                "new_status": "executing",
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_id=agent_name,
            aggregate_type="agent"
        )

        # Mock: Generate fake response
        mock_response = f"Mock response to: {command[:50]}..."

        # Log agent response
        self._event_store.append(
            event_type=AGENT_RESPONSE_RECEIVED,
            data={
                "agent_name": agent_name,
                "response": mock_response,
                "response_type": "text",
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_id=agent_name,
            aggregate_type="agent"
        )

        # Mock: Log fake cost
        self._event_store.append(
            event_type=COST_INCURRED,
            data={
                "agent_name": agent_name,
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.0015,
                "model": self._claude_clients.get(agent_name, {}).get("model", "claude-3-5-sonnet-20241022"),
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_id=agent_name,
            aggregate_type="agent"
        )

        # Log status change to idle
        self._event_store.append(
            event_type=AGENT_STATUS_CHANGED,
            data={
                "agent_name": agent_name,
                "old_status": "executing",
                "new_status": "idle",
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_id=agent_name,
            aggregate_type="agent"
        )

    async def _execute_orchestrator(self, data: Dict[str, Any]) -> None:
        """
        Execute orchestrator to generate response.

        This is a mock implementation. Step 10 will integrate the real SDK.

        Args:
            data: Effect data containing:
                - message: User message to respond to
        """
        message = data["message"]

        # Mock: Simulate orchestrator execution
        await asyncio.sleep(0.01)  # Simulate async work

        # Mock: Generate fake orchestrator response
        mock_response = f"Mock orchestrator response to: {message[:50]}..."

        # Log orchestrator response
        self._event_store.append(
            event_type=ORCHESTRATOR_RESPONSE_GENERATED,
            data={
                "sender": "orchestrator",
                "receiver": "user",
                "message": mock_response,
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_type="chat"
        )

        # Mock: Log fake cost for orchestrator
        self._event_store.append(
            event_type=COST_INCURRED,
            data={
                "agent_name": "orchestrator",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost": 0.003,
                "model": "claude-3-5-sonnet-20241022",
                "timestamp": datetime.utcnow().isoformat(),
            },
            aggregate_type="orchestrator"
        )


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "EffectExecutor",
]
