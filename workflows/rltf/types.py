"""
RLTF Types - 基于工具反馈的强化学习综合序列优化类型定义

定义 RLTF 系统中使用的所有数据结构和类型。
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RLTFStatus(Enum):
    """RLTF 运行状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PPAMetrics:
    """
    Power, Performance, Area 指标

    用于评估电路优化效果的核心指标。
    """
    area: int                           # 门数量或面积单位
    delay: float                        # 关键路径延迟 (ns)
    power: Optional[float] = None       # 功耗 (可选)
    node_count: Optional[int] = None    # 节点数量
    edge_count: Optional[int] = None    # 边数量
    levels: Optional[int] = None        # 逻辑层级数
    metrics_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "area": self.area,
            "delay": self.delay,
            "power": self.power,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "levels": self.levels,
            "metrics_valid": self.metrics_valid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PPAMetrics":
        """从字典创建"""
        return cls(
            area=data["area"],
            delay=data["delay"],
            power=data.get("power"),
            node_count=data.get("node_count"),
            edge_count=data.get("edge_count"),
            levels=data.get("levels"),
            metrics_valid=data.get("metrics_valid", True),
        )


@dataclass
class RLTFConfig:
    """
    RLTF 配置参数

    控制 RLTF 优化流程的所有配置选项。
    """
    aig_file_path: str                          # AIG 文件路径
    max_iterations: int = 50                    # 最大迭代次数
    convergence_threshold: float = 0.01         # 收敛阈值
    target_area: Optional[int] = None           # 目标面积
    target_delay: Optional[float] = None        # 目标延迟
    target_power: Optional[float] = None        # 目标功耗
    llm_model: str = "deepseek-chat"           # LLM 模型
    temperature: float = 0.7                    # LLM 温度
    abc_timeout: int = 30                       # ABC 超时时间（秒）
    sta_timeout: int = 60                       # OpenSTA 超时时间（秒）
    session_id: Optional[str] = None            # 会话 ID
    enable_checkpoints: bool = True             # 启用检查点
    checkpoint_interval: int = 10               # 检查点间隔

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "aig_file_path": self.aig_file_path,
            "max_iterations": self.max_iterations,
            "convergence_threshold": self.convergence_threshold,
            "target_area": self.target_area,
            "target_delay": self.target_delay,
            "target_power": self.target_power,
            "llm_model": self.llm_model,
            "temperature": self.temperature,
            "abc_timeout": self.abc_timeout,
            "sta_timeout": self.sta_timeout,
            "session_id": self.session_id,
            "enable_checkpoints": self.enable_checkpoints,
            "checkpoint_interval": self.checkpoint_interval,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RLTFConfig":
        """从字典创建"""
        return cls(**data)


@dataclass
class RLTFIteration:
    """
    单次迭代记录

    记录每次 RL 迭代的完整信息，包括输入、输出、指标和 Reward。
    """
    iteration_id: int                           # 迭代 ID
    timestamp: datetime                         # 时间戳
    abc_sequence: str                           # ABC 命令序列
    abc_output: str                             # ABC 输出
    abc_success: bool                           # ABC 是否成功
    abc_duration: float                         # ABC 执行时间（秒）
    sta_output: Optional[str] = None            # OpenSTA 输出
    sta_success: Optional[bool] = None          # OpenSTA 是否成功
    sta_duration: Optional[float] = None        # OpenSTA 执行时间（秒）
    metrics: Optional[PPAMetrics] = None        # PPA 指标
    reward: float = 0.0                         # 当前 Reward
    cumulative_reward: float = 0.0              # 累积 Reward
    is_best_so_far: bool = False                # 是否为当前最佳
    convergence_score: Optional[float] = None   # 收敛分数

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "iteration_id": self.iteration_id,
            "timestamp": self.timestamp.isoformat(),
            "abc_sequence": self.abc_sequence,
            "abc_output": self.abc_output,
            "abc_success": self.abc_success,
            "abc_duration": self.abc_duration,
            "sta_output": self.sta_output,
            "sta_success": self.sta_success,
            "sta_duration": self.sta_duration,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "reward": self.reward,
            "cumulative_reward": self.cumulative_reward,
            "is_best_so_far": self.is_best_so_far,
            "convergence_score": self.convergence_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RLTFIteration":
        """从字典创建"""
        return cls(
            iteration_id=data["iteration_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            abc_sequence=data["abc_sequence"],
            abc_output=data["abc_output"],
            abc_success=data["abc_success"],
            abc_duration=data["abc_duration"],
            sta_output=data.get("sta_output"),
            sta_success=data.get("sta_success"),
            sta_duration=data.get("sta_duration"),
            metrics=PPAMetrics.from_dict(data["metrics"]) if data.get("metrics") else None,
            reward=data["reward"],
            cumulative_reward=data["cumulative_reward"],
            is_best_so_far=data["is_best_so_far"],
            convergence_score=data.get("convergence_score"),
        )


@dataclass
class RLTFState:
    """
    RLTF 运行状态

    维护整个 RLTF 优化流程的状态信息。
    """
    session_id: str                                     # 会话 ID
    config: RLTFConfig                                  # 配置
    status: RLTFStatus = RLTFStatus.IDLE               # 当前状态
    current_iteration: int = 0                          # 当前迭代次数
    iterations: List[RLTFIteration] = field(default_factory=list)  # 迭代历史
    best_iteration: Optional[RLTFIteration] = None      # 最佳迭代
    best_metrics: Optional[PPAMetrics] = None           # 最佳指标
    start_time: Optional[datetime] = None               # 开始时间
    end_time: Optional[datetime] = None                 # 结束时间
    total_duration: Optional[float] = None              # 总耗时（秒）
    errors: List[Dict[str, Any]] = field(default_factory=list)  # 错误记录

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "current_iteration": self.current_iteration,
            "iterations": [it.to_dict() for it in self.iterations],
            "best_iteration": self.best_iteration.to_dict() if self.best_iteration else None,
            "best_metrics": self.best_metrics.to_dict() if self.best_metrics else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration": self.total_duration,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RLTFState":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            config=RLTFConfig.from_dict(data["config"]),
            status=RLTFStatus(data["status"]),
            current_iteration=data["current_iteration"],
            iterations=[RLTFIteration.from_dict(it) for it in data["iterations"]],
            best_iteration=RLTFIteration.from_dict(data["best_iteration"]) if data.get("best_iteration") else None,
            best_metrics=PPAMetrics.from_dict(data["best_metrics"]) if data.get("best_metrics") else None,
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            total_duration=data.get("total_duration"),
            errors=data.get("errors", []),
        )


@dataclass
class RLTFResult:
    """
    RLTF 最终结果

    封装 RLTF 优化流程的最终结果和统计信息。
    """
    success: bool                                       # 是否成功
    state: RLTFState                                    # 最终状态
    best_sequence: Optional[str] = None                 # 最佳序列
    best_metrics: Optional[PPAMetrics] = None           # 最佳指标
    improvement: Optional[Dict[str, float]] = None      # 改进百分比
    summary: str = ""                                   # 摘要信息

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "state": self.state.to_dict(),
            "best_sequence": self.best_sequence,
            "best_metrics": self.best_metrics.to_dict() if self.best_metrics else None,
            "improvement": self.improvement,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RLTFResult":
        """从字典创建"""
        return cls(
            success=data["success"],
            state=RLTFState.from_dict(data["state"]),
            best_sequence=data.get("best_sequence"),
            best_metrics=PPAMetrics.from_dict(data["best_metrics"]) if data.get("best_metrics") else None,
            improvement=data.get("improvement"),
            summary=data.get("summary", ""),
        )


@dataclass
class SequenceGenerationContext:
    """
    序列生成上下文

    提供给 LLM 的上下文信息，用于生成下一个 ABC 序列。
    """
    current_iteration: int                              # 当前迭代次数
    previous_sequences: List[str]                       # 历史序列
    previous_rewards: List[float]                       # 历史 Reward
    best_sequence: Optional[str] = None                 # 当前最佳序列
    best_reward: Optional[float] = None                 # 当前最佳 Reward
    current_metrics: Optional[PPAMetrics] = None        # 当前指标
    target_metrics: Optional[Dict[str, float]] = None   # 目标指标
