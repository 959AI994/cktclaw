"""
RLTF (Reinforcement Learning from Tool Feedback) Workflow

基于工具反馈的强化学习综合序列优化模块。

主要组件：
- RLTFCoordinator: 主协调器
- RLTFConfig: 配置类
- RLTFResult: 结果类
- PPAMetrics: PPA 指标类
"""

from .types import (
    RLTFStatus,
    PPAMetrics,
    RLTFConfig,
    RLTFIteration,
    RLTFState,
    RLTFResult,
    SequenceGenerationContext,
)

from .coordinator import RLTFCoordinator
from .state import RLTFStateManager
from .reward import RLTFRewardCalculator
from .sequence_generator import RLTFSequenceGenerator
from .executor import RLTFExecutor
from .persistence import RLTFPersistence

__all__ = [
    # Types
    "RLTFStatus",
    "PPAMetrics",
    "RLTFConfig",
    "RLTFIteration",
    "RLTFState",
    "RLTFResult",
    "SequenceGenerationContext",

    # Core Components
    "RLTFCoordinator",
    "RLTFStateManager",
    "RLTFRewardCalculator",
    "RLTFSequenceGenerator",
    "RLTFExecutor",
    "RLTFPersistence",
]

__version__ = "0.1.0"
