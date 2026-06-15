"""
CktClaw Loop — Cross-domain closed-loop system.

Four-phase cycle:
1. DEFINE:   GoalDecomposer → CrossLayerTaskGraph
2. GENERATE: Domain teams produce artifacts in parallel
3. VERIFY:   Real tool chain verification + metrics
4. EVOLVE:   Bottleneck analysis + experience → feedback
"""

from .task_graph import TaskNode, CrossLayerTaskGraph
from .goal_decomposer import GoalDecomposer
from .domain_teams import DomainTeam, EDATeam, ChipTeam, AIInfraTeam
from .verification import VerificationRunner, VerificationReport
from .evolution import (
    ExperienceRecord,
    ExperienceStore,
    BottleneckAnalyzer,
    FeedbackGenerator,
    ConvergenceChecker,
)
from .controller import SystemLoopController, LoopConfig, LoopResult

__all__ = [
    "TaskNode",
    "CrossLayerTaskGraph",
    "GoalDecomposer",
    "DomainTeam",
    "EDATeam",
    "ChipTeam",
    "AIInfraTeam",
    "VerificationRunner",
    "VerificationReport",
    "ExperienceRecord",
    "ExperienceStore",
    "BottleneckAnalyzer",
    "FeedbackGenerator",
    "ConvergenceChecker",
    "SystemLoopController",
    "LoopConfig",
    "LoopResult",
]
