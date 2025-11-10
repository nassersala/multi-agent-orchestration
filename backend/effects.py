"""
Effect definitions for command handling.

Effects represent side effects that need to be executed after commands
generate events. They are separate from events to maintain pure function
semantics in the command handler.
"""

from dataclasses import dataclass
from typing import Dict, Any, Literal


# ═══════════════════════════════════════════════════════════
# EFFECT TYPES
# ═══════════════════════════════════════════════════════════

EffectType = Literal[
    'create_claude_client',
    'execute_agent_command',
    'execute_orchestrator'
]


# ═══════════════════════════════════════════════════════════
# EFFECT MODEL
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Effect:
    """
    Immutable side effect to be executed.

    Effects are produced by command handlers alongside events.
    They represent actions that need to happen in the outside world
    (creating Claude clients, executing agents, etc.).

    The command handler remains pure by returning effects rather than
    executing them directly. The effect executor handles the actual
    side effect execution.

    Attributes:
        type: The type of effect to execute
        data: Payload data needed to execute the effect
    """
    type: EffectType
    data: Dict[str, Any]


# ═══════════════════════════════════════════════════════════
# EXPORT PUBLIC API
# ═══════════════════════════════════════════════════════════

__all__ = [
    "Effect",
    "EffectType",
]
