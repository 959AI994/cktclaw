"""
Pareto Multi-Agent Negotiation - 博弈论驱动的多智能体协商协议

驱动帕累托最优 PPA 的多智能体协商系统。
"""

from .types import (
    AgentType,
    VoteType,
    NegotiationStatus,
    PPAMetrics,
    Proposal,
    Vote,
    NegotiationRound,
    NegotiationState,
    NegotiationConfig,
    NegotiationResult,
)

from .agents import (
    BaseAgent,
    AreaAgent,
    DelayAgent,
    PowerAgent,
)

from .arbiter import NashArbiter
from .pareto_tracker import ParetoTracker
from .coordinator import NegotiationCoordinator
from .persistence import NegotiationPersistence

__all__ = [
    # Types
    "AgentType",
    "VoteType",
    "NegotiationStatus",
    "PPAMetrics",
    "Proposal",
    "Vote",
    "NegotiationRound",
    "NegotiationState",
    "NegotiationConfig",
    "NegotiationResult",
    # Agents
    "BaseAgent",
    "AreaAgent",
    "DelayAgent",
    "PowerAgent",
    # Core
    "NashArbiter",
    "ParetoTracker",
    "NegotiationCoordinator",
    "NegotiationPersistence",
]
