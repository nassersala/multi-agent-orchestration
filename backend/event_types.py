"""
Event type constants for the event sourcing system.

All events that can occur in the multi-agent orchestration system.
These constants ensure type safety and consistency across the codebase.
"""

# ═══════════════════════════════════════════════════════════
# ORCHESTRATOR EVENTS
# ═══════════════════════════════════════════════════════════

ORCHESTRATOR_INITIALIZED = "ORCHESTRATOR_INITIALIZED"
"""Orchestrator system has been initialized with a new session."""

ORCHESTRATOR_STATUS_CHANGED = "ORCHESTRATOR_STATUS_CHANGED"
"""Orchestrator status changed (idle, executing, waiting, blocked, complete)."""

ORCHESTRATOR_RESPONSE_GENERATED = "ORCHESTRATOR_RESPONSE_GENERATED"
"""Orchestrator generated a response to user."""


# ═══════════════════════════════════════════════════════════
# AGENT LIFECYCLE EVENTS
# ═══════════════════════════════════════════════════════════

AGENT_CREATED = "AGENT_CREATED"
"""New agent was created by orchestrator."""

AGENT_COMMANDED = "AGENT_COMMANDED"
"""Agent received a command/prompt to execute."""

AGENT_STATUS_CHANGED = "AGENT_STATUS_CHANGED"
"""Agent status changed (idle, executing, waiting, blocked, complete)."""

AGENT_DELETED = "AGENT_DELETED"
"""Agent was deleted/archived."""

AGENT_RESPONSE_RECEIVED = "AGENT_RESPONSE_RECEIVED"
"""Agent produced a response (text, thinking, or tool use)."""


# ═══════════════════════════════════════════════════════════
# CHAT & MESSAGING EVENTS
# ═══════════════════════════════════════════════════════════

USER_MESSAGE_RECEIVED = "USER_MESSAGE_RECEIVED"
"""User sent a message to the orchestrator."""

CHAT_MESSAGE_ADDED = "CHAT_MESSAGE_ADDED"
"""Generic chat message added (user, orchestrator, or agent)."""


# ═══════════════════════════════════════════════════════════
# TOOL & EXECUTION EVENTS
# ═══════════════════════════════════════════════════════════

TOOL_INVOKED = "TOOL_INVOKED"
"""Agent invoked a tool (Read, Write, Bash, etc.)."""

TOOL_RESULT_RECEIVED = "TOOL_RESULT_RECEIVED"
"""Tool execution completed and returned result."""


# ═══════════════════════════════════════════════════════════
# COST & METRICS EVENTS
# ═══════════════════════════════════════════════════════════

COST_INCURRED = "COST_INCURRED"
"""Tokens consumed and cost incurred for API call."""

METRICS_UPDATED = "METRICS_UPDATED"
"""Performance or usage metrics updated."""


# ═══════════════════════════════════════════════════════════
# EFFECT & ERROR EVENTS
# ═══════════════════════════════════════════════════════════

EFFECT_EXECUTION_FAILED = "EFFECT_EXECUTION_FAILED"
"""Side effect execution failed (create agent, invoke tool, etc.)."""

ERROR_OCCURRED = "ERROR_OCCURRED"
"""Generic error event."""


# ═══════════════════════════════════════════════════════════
# SESSION & STATE EVENTS
# ═══════════════════════════════════════════════════════════

SESSION_STARTED = "SESSION_STARTED"
"""New session started."""

SESSION_ENDED = "SESSION_ENDED"
"""Session ended or archived."""

STATE_SNAPSHOT = "STATE_SNAPSHOT"
"""Complete state snapshot for SSE clients (not stored in event log)."""


# ═══════════════════════════════════════════════════════════
# EXPORT ALL EVENT TYPES
# ═══════════════════════════════════════════════════════════

__all__ = [
    # Orchestrator
    "ORCHESTRATOR_INITIALIZED",
    "ORCHESTRATOR_STATUS_CHANGED",
    "ORCHESTRATOR_RESPONSE_GENERATED",
    # Agents
    "AGENT_CREATED",
    "AGENT_COMMANDED",
    "AGENT_STATUS_CHANGED",
    "AGENT_DELETED",
    "AGENT_RESPONSE_RECEIVED",
    # Chat
    "USER_MESSAGE_RECEIVED",
    "CHAT_MESSAGE_ADDED",
    # Tools
    "TOOL_INVOKED",
    "TOOL_RESULT_RECEIVED",
    # Cost
    "COST_INCURRED",
    "METRICS_UPDATED",
    # Effects/Errors
    "EFFECT_EXECUTION_FAILED",
    "ERROR_OCCURRED",
    # Session
    "SESSION_STARTED",
    "SESSION_ENDED",
    "STATE_SNAPSHOT",
]
