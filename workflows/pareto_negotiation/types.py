"""
Pareto Multi-Agent Negotiation Types - 协商类型定义

定义博弈论驱动的多智能体协商协议的核心数据结构。
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class AgentType(Enum):
    """智能体类型"""
    AREA = "area"           # 面积优化 Agent
    DELAY = "delay"         # 延迟优化 Agent
    POWER = "power"         # 功耗优化 Agent


class VoteType(Enum):
    """投票类型"""
    SUPPORT = "support"     # 支持
    OPPOSE = "oppose"       # 反对
    NEUTRAL = "neutral"     # 中立


class NegotiationStatus(Enum):
    """协商状态"""
    IDLE = "idle"
    PROPOSING = "proposing"     # 提案阶段
    VOTING = "voting"           # 投票阶段
    ARBITRATING = "arbitrating" # 仲裁阶段
    EXECUTING = "executing"     # 执行阶段
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PPAMetrics:
    """
    Power, Performance, Area 指标

    复用 RLTF 的 PPAMetrics 定义，确保兼容性。
    """
    area: int                           # 面积（门数量）
    delay: float                        # 延迟（ns）
    power: Optional[float] = None       # 功耗（mW）
    node_count: Optional[int] = None
    edge_count: Optional[int] = None
    levels: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "area": self.area,
            "delay": self.delay,
            "power": self.power,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "levels": self.levels,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PPAMetrics":
        """从字典反序列化"""
        return cls(**data)

    def dominates(self, other: "PPAMetrics") -> bool:
        """
        判断是否 Pareto 支配另一个指标

        如果在所有目标上都不差于 other，且至少在一个目标上严格优于 other，
        则称 self 支配 other。

        Args:
            other: 另一个 PPA 指标

        Returns:
            是否支配
        """
        # 面积：越小越好
        area_better = self.area <= other.area
        area_strictly_better = self.area < other.area

        # 延迟：越小越好
        delay_better = self.delay <= other.delay
        delay_strictly_better = self.delay < other.delay

        # 功耗：越小越好（如果有）
        power_better = True
        power_strictly_better = False
        if self.power is not None and other.power is not None:
            power_better = self.power <= other.power
            power_strictly_better = self.power < other.power

        # 所有目标都不差于 other
        all_better = area_better and delay_better and power_better

        # 至少一个目标严格优于 other
        any_strictly_better = (
            area_strictly_better or
            delay_strictly_better or
            power_strictly_better
        )

        return all_better and any_strictly_better


@dataclass
class Proposal:
    """
    提案

    每个 Agent 在每轮协商中提出的优化方案。
    """
    proposal_id: str                    # 提案 ID
    agent_type: AgentType               # 提案者类型
    abc_sequence: str                   # ABC 优化序列
    rationale: str                      # 提案理由
    expected_improvement: Dict[str, float]  # 预期改进（area/delay/power）
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "proposal_id": self.proposal_id,
            "agent_type": self.agent_type.value,
            "abc_sequence": self.abc_sequence,
            "rationale": self.rationale,
            "expected_improvement": self.expected_improvement,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Proposal":
        """从字典反序列化"""
        return cls(
            proposal_id=data["proposal_id"],
            agent_type=AgentType(data["agent_type"]),
            abc_sequence=data["abc_sequence"],
            rationale=data["rationale"],
            expected_improvement=data["expected_improvement"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class Vote:
    """
    投票

    Agent 对其他 Agent 提案的投票。
    """
    voter_type: AgentType               # 投票者类型
    proposal_id: str                    # 被投票的提案 ID
    vote_type: VoteType                 # 投票类型
    utility_score: float                # 效用分数（从投票者角度）
    reasoning: str                      # 投票理由
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "voter_type": self.voter_type.value,
            "proposal_id": self.proposal_id,
            "vote_type": self.vote_type.value,
            "utility_score": self.utility_score,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Vote":
        """从字典反序列化"""
        return cls(
            voter_type=AgentType(data["voter_type"]),
            proposal_id=data["proposal_id"],
            vote_type=VoteType(data["vote_type"]),
            utility_score=data["utility_score"],
            reasoning=data["reasoning"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class NegotiationRound:
    """
    协商轮次

    记录一轮完整的协商过程：提案 → 投票 → 仲裁 → 执行。
    """
    round_id: int                       # 轮次 ID
    timestamp: datetime                 # 时间戳

    # 提案阶段
    proposals: List[Proposal] = field(default_factory=list)

    # 投票阶段
    votes: List[Vote] = field(default_factory=list)

    # 仲裁阶段
    selected_proposal: Optional[Proposal] = None
    nash_equilibrium_score: Optional[float] = None
    arbiter_reasoning: str = ""

    # 执行阶段
    execution_success: bool = False
    execution_duration: float = 0.0
    execution_output: str = ""

    # 结果
    resulting_metrics: Optional[PPAMetrics] = None
    is_pareto_optimal: bool = False
    improvement_over_previous: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "round_id": self.round_id,
            "timestamp": self.timestamp.isoformat(),
            "proposals": [p.to_dict() for p in self.proposals],
            "votes": [v.to_dict() for v in self.votes],
            "selected_proposal": self.selected_proposal.to_dict() if self.selected_proposal else None,
            "nash_equilibrium_score": self.nash_equilibrium_score,
            "arbiter_reasoning": self.arbiter_reasoning,
            "execution_success": self.execution_success,
            "execution_duration": self.execution_duration,
            "execution_output": self.execution_output,
            "resulting_metrics": self.resulting_metrics.to_dict() if self.resulting_metrics else None,
            "is_pareto_optimal": self.is_pareto_optimal,
            "improvement_over_previous": self.improvement_over_previous,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NegotiationRound":
        """从字典反序列化"""
        return cls(
            round_id=data["round_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            proposals=[Proposal.from_dict(p) for p in data["proposals"]],
            votes=[Vote.from_dict(v) for v in data["votes"]],
            selected_proposal=Proposal.from_dict(data["selected_proposal"]) if data["selected_proposal"] else None,
            nash_equilibrium_score=data["nash_equilibrium_score"],
            arbiter_reasoning=data["arbiter_reasoning"],
            execution_success=data["execution_success"],
            execution_duration=data["execution_duration"],
            execution_output=data["execution_output"],
            resulting_metrics=PPAMetrics.from_dict(data["resulting_metrics"]) if data["resulting_metrics"] else None,
            is_pareto_optimal=data["is_pareto_optimal"],
            improvement_over_previous=data["improvement_over_previous"],
        )


@dataclass
class NegotiationState:
    """
    协商状态

    维护整个协商过程的状态。
    """
    session_id: str                     # 会话 ID
    config: "NegotiationConfig"         # 配置
    status: NegotiationStatus = NegotiationStatus.IDLE

    # 协商历史
    current_round: int = 0
    rounds: List[NegotiationRound] = field(default_factory=list)

    # 当前最佳
    current_metrics: Optional[PPAMetrics] = None
    initial_metrics: Optional[PPAMetrics] = None

    # Pareto 前沿
    pareto_front: List[PPAMetrics] = field(default_factory=list)

    # 时间统计
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration: float = 0.0

    # 错误记录
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "current_round": self.current_round,
            "rounds": [r.to_dict() for r in self.rounds],
            "current_metrics": self.current_metrics.to_dict() if self.current_metrics else None,
            "initial_metrics": self.initial_metrics.to_dict() if self.initial_metrics else None,
            "pareto_front": [m.to_dict() for m in self.pareto_front],
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration": self.total_duration,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NegotiationState":
        """从字典反序列化"""
        from .types import NegotiationConfig  # 避免循环导入

        return cls(
            session_id=data["session_id"],
            config=NegotiationConfig.from_dict(data["config"]),
            status=NegotiationStatus(data["status"]),
            current_round=data["current_round"],
            rounds=[NegotiationRound.from_dict(r) for r in data["rounds"]],
            current_metrics=PPAMetrics.from_dict(data["current_metrics"]) if data["current_metrics"] else None,
            initial_metrics=PPAMetrics.from_dict(data["initial_metrics"]) if data["initial_metrics"] else None,
            pareto_front=[PPAMetrics.from_dict(m) for m in data["pareto_front"]],
            start_time=datetime.fromisoformat(data["start_time"]) if data["start_time"] else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data["end_time"] else None,
            total_duration=data["total_duration"],
            errors=data["errors"],
        )


@dataclass
class NegotiationConfig:
    """
    协商配置
    """
    aig_file_path: str                  # AIG 文件路径
    max_rounds: int = 50                # 最大协商轮次
    agents: List[AgentType] = field(default_factory=lambda: [
        AgentType.AREA,
        AgentType.DELAY,
        AgentType.POWER,
    ])

    # 目标约束
    target_area: Optional[int] = None
    target_delay: Optional[float] = None
    target_power: Optional[float] = None

    # 协商参数
    convergence_threshold: float = 0.01  # 收敛阈值
    nash_epsilon: float = 0.1            # Nash 均衡容差

    # 执行参数
    abc_timeout: int = 30
    sta_timeout: int = 60

    # 持久化
    session_id: Optional[str] = None
    enable_checkpoints: bool = True
    checkpoint_interval: int = 5

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "aig_file_path": self.aig_file_path,
            "max_rounds": self.max_rounds,
            "agents": [a.value for a in self.agents],
            "target_area": self.target_area,
            "target_delay": self.target_delay,
            "target_power": self.target_power,
            "convergence_threshold": self.convergence_threshold,
            "nash_epsilon": self.nash_epsilon,
            "abc_timeout": self.abc_timeout,
            "sta_timeout": self.sta_timeout,
            "session_id": self.session_id,
            "enable_checkpoints": self.enable_checkpoints,
            "checkpoint_interval": self.checkpoint_interval,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NegotiationConfig":
        """从字典反序列化"""
        return cls(
            aig_file_path=data["aig_file_path"],
            max_rounds=data["max_rounds"],
            agents=[AgentType(a) for a in data["agents"]],
            target_area=data.get("target_area"),
            target_delay=data.get("target_delay"),
            target_power=data.get("target_power"),
            convergence_threshold=data["convergence_threshold"],
            nash_epsilon=data["nash_epsilon"],
            abc_timeout=data["abc_timeout"],
            sta_timeout=data["sta_timeout"],
            session_id=data.get("session_id"),
            enable_checkpoints=data["enable_checkpoints"],
            checkpoint_interval=data["checkpoint_interval"],
        )


@dataclass
class NegotiationResult:
    """
    协商结果
    """
    success: bool
    state: NegotiationState

    # 最终结果
    final_metrics: Optional[PPAMetrics] = None
    pareto_front: List[PPAMetrics] = field(default_factory=list)

    # 改进统计
    improvement: Optional[Dict[str, float]] = None

    # 协商统计
    total_rounds: int = 0
    successful_rounds: int = 0
    pareto_optimal_rounds: int = 0

    # 摘要
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "state": self.state.to_dict(),
            "final_metrics": self.final_metrics.to_dict() if self.final_metrics else None,
            "pareto_front": [m.to_dict() for m in self.pareto_front],
            "improvement": self.improvement,
            "total_rounds": self.total_rounds,
            "successful_rounds": self.successful_rounds,
            "pareto_optimal_rounds": self.pareto_optimal_rounds,
            "summary": self.summary,
        }
