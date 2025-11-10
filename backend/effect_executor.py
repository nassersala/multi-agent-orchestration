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
import os
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
    TOOL_INVOKED,
    TOOL_RESULT_RECEIVED,
)

# Try to import Claude SDK - fall back to mock mode if not available
try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ResultMessage,
    )
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False


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

    def __init__(self, event_store: EventStore, use_mock: Optional[bool] = None, working_dir: Optional[str] = None):
        """
        Initialize effect executor.

        Args:
            event_store: EventStore to log execution events to
            use_mock: Force mock mode (True) or real SDK (False). If None, auto-detect based on SDK availability and API key.
            working_dir: Working directory for agents (default: current directory)
        """
        self._event_store = event_store
        self._claude_clients: Dict[str, Any] = {}
        self._working_dir = working_dir or os.getcwd()

        # Determine mock vs real mode
        if use_mock is None:
            # Auto-detect: use real SDK if available and API key exists
            has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
            self._use_mock = not (CLAUDE_SDK_AVAILABLE and has_api_key)
        else:
            self._use_mock = use_mock

        if not self._use_mock and not CLAUDE_SDK_AVAILABLE:
            raise RuntimeError("Claude SDK not available but real mode requested. Install claude-agent-sdk.")

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
        Create a Claude SDK client configuration for an agent.

        Stores agent configuration for later use in execute_agent_command.

        Args:
            data: Effect data containing:
                - agent_name: Name of agent
                - model: Claude model to use
                - system_prompt: System prompt for agent
                - template: Optional template name
        """
        agent_name = data["agent_name"]
        model = data["model"]

        # Store client configuration (not actual client instance)
        self._claude_clients[agent_name] = {
            "model": model,
            "system_prompt": data["system_prompt"],
            "template": data.get("template"),
            "created_at": datetime.utcnow().isoformat(),
            "session_id": None,  # Will be updated after first execution
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
        Execute a command on an agent using Claude SDK.

        Uses mock or real SDK based on configuration.

        Args:
            data: Effect data containing:
                - agent_name: Name of agent to execute command on
                - command: Command/prompt to send to agent
        """
        if self._use_mock:
            await self._execute_agent_command_mock(data)
        else:
            await self._execute_agent_command_real(data)

    async def _execute_agent_command_mock(self, data: Dict[str, Any]) -> None:
        """Mock implementation for testing without API keys."""
        agent_name = data["agent_name"]
        command = data["command"]

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

        # Generate mock response
        mock_response = f"Mock response to: {command[:50]}..."

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

        # Log mock cost
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

    async def _execute_agent_command_real(self, data: Dict[str, Any]) -> None:
        """Real Claude SDK implementation."""
        agent_name = data["agent_name"]
        command = data["command"]

        # Get agent configuration
        agent_config = self._claude_clients.get(agent_name)
        if not agent_config:
            raise ValueError(f"Agent '{agent_name}' not configured")

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

        try:
            # Create Claude SDK options
            options = ClaudeAgentOptions(
                system_prompt=agent_config["system_prompt"],
                model=agent_config["model"],
                cwd=self._working_dir,
                resume=agent_config.get("session_id"),  # Resume previous session if available
                max_turns=10,
                permission_mode="acceptEdits",
            )

            # Execute with Claude SDK
            async with ClaudeSDKClient(options=options) as client:
                await client.query(command)

                # Process messages
                session_id, input_tokens, output_tokens, cost = await self._process_messages(
                    client, agent_name
                )

                # Update session ID for future resumes
                agent_config["session_id"] = session_id

                # Log cost
                if input_tokens or output_tokens:
                    self._event_store.append(
                        event_type=COST_INCURRED,
                        data={
                            "agent_name": agent_name,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cost": cost,
                            "model": agent_config["model"],
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        aggregate_id=agent_name,
                        aggregate_type="agent"
                    )

        finally:
            # Always log status change back to idle
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

        Uses mock orchestrator (no real implementation for now).

        Args:
            data: Effect data containing:
                - message: User message to respond to
        """
        message = data["message"]

        # For now, always use mock for orchestrator
        # Real orchestrator would need agent management tools, etc.
        await asyncio.sleep(0.01)

        mock_response = f"Mock orchestrator response to: {message[:50]}..."

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

    async def _process_messages(
        self, client: 'ClaudeSDKClient', agent_name: str
    ) -> tuple[Optional[str], int, int, float]:
        """
        Process messages from Claude SDK client.

        Args:
            client: Claude SDK client instance
            agent_name: Name of the agent

        Returns:
            Tuple of (session_id, input_tokens, output_tokens, total_cost)
        """
        session_id = None
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        async for message in client.receive_response():
            if isinstance(message, SystemMessage):
                # SystemMessages are informational, skip
                continue

            elif isinstance(message, AssistantMessage):
                # Process each block in the message
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Log text response
                        self._event_store.append(
                            event_type=AGENT_RESPONSE_RECEIVED,
                            data={
                                "agent_name": agent_name,
                                "response": block.text,
                                "response_type": "text",
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            aggregate_id=agent_name,
                            aggregate_type="agent"
                        )

                    elif isinstance(block, ThinkingBlock):
                        # Log thinking block
                        self._event_store.append(
                            event_type=AGENT_RESPONSE_RECEIVED,
                            data={
                                "agent_name": agent_name,
                                "response": block.thinking,
                                "response_type": "thinking",
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            aggregate_id=agent_name,
                            aggregate_type="agent"
                        )

                    elif isinstance(block, ToolUseBlock):
                        # Log tool invocation
                        self._event_store.append(
                            event_type=TOOL_INVOKED,
                            data={
                                "agent_name": agent_name,
                                "tool_name": block.name,
                                "tool_input": block.input,
                                "tool_use_id": block.id,
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            aggregate_id=agent_name,
                            aggregate_type="agent"
                        )

            elif isinstance(message, ResultMessage):
                # Extract session ID
                session_id = message.session_id

                # Extract usage and cost
                if message.usage:
                    usage = message.usage
                    if isinstance(usage, dict):
                        total_input_tokens = usage.get("input_tokens", 0)
                        total_output_tokens = usage.get("output_tokens", 0)
                    else:
                        total_input_tokens = getattr(usage, "input_tokens", 0)
                        total_output_tokens = getattr(usage, "output_tokens", 0)

                # Extract cost
                total_cost = getattr(message, "total_cost_usd", None) or 0.0
                if total_cost == 0.0 and message.usage:
                    if isinstance(message.usage, dict):
                        total_cost = message.usage.get("total_cost_usd", 0.0)
                    else:
                        total_cost = getattr(message.usage, "total_cost_usd", 0.0)

        return session_id, total_input_tokens, total_output_tokens, total_cost


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "EffectExecutor",
]
