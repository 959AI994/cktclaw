"""
Pareto Multi-Agent Negotiation Agents - 专业智能体

三个专业 Agent：AreaAgent, DelayAgent, PowerAgent
每个 Agent 维护自己的目标函数和策略空间。
"""

import uuid
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime

from .types import (
    AgentType,
    VoteType,
    PPAMetrics,
    Proposal,
    Vote,
    NegotiationState,
)


class BaseAgent(ABC):
    """
    基础 Agent 抽象类

    定义所有 Agent 的通用接口。
    """

    def __init__(self, agent_type: AgentType):
        """
        初始化 Agent

        Args:
            agent_type: Agent 类型
        """
        self.agent_type = agent_type
        self.proposal_history: List[Proposal] = []
        self.vote_history: List[Vote] = []

    @abstractmethod
    def generate_proposal(
        self,
        state: NegotiationState,
        current_metrics: PPAMetrics,
    ) -> Proposal:
        """
        生成提案

        Args:
            state: 当前协商状态
            current_metrics: 当前 PPA 指标

        Returns:
            提案
        """
        pass

    @abstractmethod
    def vote_on_proposal(
        self,
        proposal: Proposal,
        current_metrics: PPAMetrics,
        state: NegotiationState,
    ) -> Vote:
        """
        对提案投票

        Args:
            proposal: 待投票的提案
            current_metrics: 当前 PPA 指标
            state: 当前协商状态

        Returns:
            投票
        """
        pass

    @abstractmethod
    def calculate_utility(
        self,
        metrics: PPAMetrics,
        baseline: PPAMetrics,
    ) -> float:
        """
        计算效用函数

        Args:
            metrics: 当前指标
            baseline: 基准指标

        Returns:
            效用值（越大越好）
        """
        pass

    def _generate_proposal_id(self) -> str:
        """生成提案 ID"""
        return f"{self.agent_type.value}_{uuid.uuid4().hex[:8]}"


class AreaAgent(BaseAgent):
    """
    面积优化 Agent

    目标：最小化电路面积（门数量）
    策略：提出面积优化导向的 ABC 序列
    """

    # 面积优化序列池
    AREA_OPTIMIZATION_SEQUENCES = [
        "strash; rewrite; refactor",
        "strash; rewrite; rewrite; refactor",
        "strash; rewrite; refactor; rewrite",
        "strash; compress",
        "strash; compress2",
        "strash; rewrite; resub",
        "strash; rewrite; resub; rewrite",
        "strash; balance; rewrite; refactor",
        "strash; rewrite; refactor; resub",
        "strash; compress; rewrite",
    ]

    def __init__(self):
        super().__init__(AgentType.AREA)
        self.sequence_index = 0

    def generate_proposal(
        self,
        state: NegotiationState,
        current_metrics: PPAMetrics,
    ) -> Proposal:
        """
        生成面积优化提案

        策略：
        1. 从面积优化序列池中选择
        2. 根据历史反馈调整选择
        3. 避免重复最近失败的序列
        """
        # 选择序列（循环遍历）
        sequence = self.AREA_OPTIMIZATION_SEQUENCES[
            self.sequence_index % len(self.AREA_OPTIMIZATION_SEQUENCES)
        ]
        self.sequence_index += 1

        # 如果有历史，尝试避免最近失败的序列
        if len(state.rounds) > 0:
            recent_rounds = state.rounds[-3:]
            failed_sequences = [
                r.selected_proposal.abc_sequence
                for r in recent_rounds
                if r.selected_proposal and not r.execution_success
            ]

            # 如果当前序列最近失败过，跳到下一个
            if sequence in failed_sequences:
                self.sequence_index += 1
                sequence = self.AREA_OPTIMIZATION_SEQUENCES[
                    self.sequence_index % len(self.AREA_OPTIMIZATION_SEQUENCES)
                ]

        # 预期改进（基于经验估计）
        expected_improvement = {
            "area": 10.0,   # 预期面积减少 10%
            "delay": -2.0,  # 可能延迟增加 2%
            "power": 0.0,   # 功耗变化不确定
        }

        proposal = Proposal(
            proposal_id=self._generate_proposal_id(),
            agent_type=self.agent_type,
            abc_sequence=sequence,
            rationale=f"Area-focused optimization using {sequence.split(';')[1].strip()} strategy",
            expected_improvement=expected_improvement,
        )

        self.proposal_history.append(proposal)
        return proposal

    def vote_on_proposal(
        self,
        proposal: Proposal,
        current_metrics: PPAMetrics,
        state: NegotiationState,
    ) -> Vote:
        """
        对提案投票

        投票策略：
        - 如果提案预期改善面积，支持
        - 如果提案预期恶化面积超过阈值，反对
        - 否则中立
        """
        expected_area_change = proposal.expected_improvement.get("area", 0.0)

        # 计算效用分数（从面积 Agent 角度）
        utility_score = expected_area_change / 100.0  # 归一化到 [0, 1]

        # 投票决策
        if expected_area_change > 5.0:
            vote_type = VoteType.SUPPORT
            reasoning = f"Supports area reduction of {expected_area_change:.1f}%"
        elif expected_area_change < -5.0:
            vote_type = VoteType.OPPOSE
            reasoning = f"Opposes area increase of {-expected_area_change:.1f}%"
        else:
            vote_type = VoteType.NEUTRAL
            reasoning = "Neutral on minor area impact"

        vote = Vote(
            voter_type=self.agent_type,
            proposal_id=proposal.proposal_id,
            vote_type=vote_type,
            utility_score=utility_score,
            reasoning=reasoning,
        )

        self.vote_history.append(vote)
        return vote

    def calculate_utility(
        self,
        metrics: PPAMetrics,
        baseline: PPAMetrics,
    ) -> float:
        """
        计算面积效用函数

        效用 = (baseline_area - current_area) / baseline_area
        """
        if baseline.area == 0:
            return 0.0

        area_improvement = (baseline.area - metrics.area) / baseline.area
        return area_improvement


class DelayAgent(BaseAgent):
    """
    延迟优化 Agent

    目标：最小化关键路径延迟
    策略：提出时序优化导向的 ABC 序列
    """

    # 延迟优化序列池
    DELAY_OPTIMIZATION_SEQUENCES = [
        "strash; balance",
        "strash; balance; rewrite; balance",
        "strash; balance; balance",
        "strash; retime",
        "strash; balance; retime",
        "strash; balance; rewrite; balance; retime",
        "strash; dch",
        "strash; balance; dch",
        "strash; balance; rewrite; dch",
        "strash; balance; compress; balance",
    ]

    def __init__(self):
        super().__init__(AgentType.DELAY)
        self.sequence_index = 0

    def generate_proposal(
        self,
        state: NegotiationState,
        current_metrics: PPAMetrics,
    ) -> Proposal:
        """
        生成延迟优化提案

        策略：
        1. 从延迟优化序列池中选择
        2. 优先选择 balance 和 retime 命令
        3. 根据历史反馈调整
        """
        sequence = self.DELAY_OPTIMIZATION_SEQUENCES[
            self.sequence_index % len(self.DELAY_OPTIMIZATION_SEQUENCES)
        ]
        self.sequence_index += 1

        # 避免最近失败的序列
        if len(state.rounds) > 0:
            recent_rounds = state.rounds[-3:]
            failed_sequences = [
                r.selected_proposal.abc_sequence
                for r in recent_rounds
                if r.selected_proposal and not r.execution_success
            ]

            if sequence in failed_sequences:
                self.sequence_index += 1
                sequence = self.DELAY_OPTIMIZATION_SEQUENCES[
                    self.sequence_index % len(self.DELAY_OPTIMIZATION_SEQUENCES)
                ]

        # 预期改进
        expected_improvement = {
            "area": -5.0,   # 可能面积增加 5%
            "delay": 15.0,  # 预期延迟减少 15%
            "power": 0.0,
        }

        proposal = Proposal(
            proposal_id=self._generate_proposal_id(),
            agent_type=self.agent_type,
            abc_sequence=sequence,
            rationale=f"Delay-focused optimization using balance/retime strategy",
            expected_improvement=expected_improvement,
        )

        self.proposal_history.append(proposal)
        return proposal

    def vote_on_proposal(
        self,
        proposal: Proposal,
        current_metrics: PPAMetrics,
        state: NegotiationState,
    ) -> Vote:
        """
        对提案投票

        投票策略：
        - 如果提案预期改善延迟，支持
        - 如果提案预期恶化延迟超过阈值，反对
        - 否则中立
        """
        expected_delay_change = proposal.expected_improvement.get("delay", 0.0)

        utility_score = expected_delay_change / 100.0

        if expected_delay_change > 5.0:
            vote_type = VoteType.SUPPORT
            reasoning = f"Supports delay reduction of {expected_delay_change:.1f}%"
        elif expected_delay_change < -5.0:
            vote_type = VoteType.OPPOSE
            reasoning = f"Opposes delay increase of {-expected_delay_change:.1f}%"
        else:
            vote_type = VoteType.NEUTRAL
            reasoning = "Neutral on minor delay impact"

        vote = Vote(
            voter_type=self.agent_type,
            proposal_id=proposal.proposal_id,
            vote_type=vote_type,
            utility_score=utility_score,
            reasoning=reasoning,
        )

        self.vote_history.append(vote)
        return vote

    def calculate_utility(
        self,
        metrics: PPAMetrics,
        baseline: PPAMetrics,
    ) -> float:
        """
        计算延迟效用函数

        效用 = (baseline_delay - current_delay) / baseline_delay
        """
        if baseline.delay == 0:
            return 0.0

        delay_improvement = (baseline.delay - metrics.delay) / baseline.delay
        return delay_improvement


class PowerAgent(BaseAgent):
    """
    功耗优化 Agent

    目标：最小化功耗
    策略：提出功耗优化导向的 ABC 序列
    """

    # 功耗优化序列池（平衡面积和延迟）
    POWER_OPTIMIZATION_SEQUENCES = [
        "strash; balance; rewrite",
        "strash; compress",
        "strash; balance; compress",
        "strash; rewrite; balance",
        "strash; balance; rewrite; balance",
        "strash; compress; balance",
        "strash; rewrite; refactor; balance",
        "strash; balance; compress2",
        "strash; compress2; balance",
        "strash; balance; rewrite; refactor; balance",
    ]

    def __init__(self):
        super().__init__(AgentType.POWER)
        self.sequence_index = 0

    def generate_proposal(
        self,
        state: NegotiationState,
        current_metrics: PPAMetrics,
    ) -> Proposal:
        """
        生成功耗优化提案

        策略：
        1. 平衡面积和延迟优化
        2. 功耗通常与面积和翻转率相关
        3. 选择综合优化序列
        """
        sequence = self.POWER_OPTIMIZATION_SEQUENCES[
            self.sequence_index % len(self.POWER_OPTIMIZATION_SEQUENCES)
        ]
        self.sequence_index += 1

        # 避免最近失败的序列
        if len(state.rounds) > 0:
            recent_rounds = state.rounds[-3:]
            failed_sequences = [
                r.selected_proposal.abc_sequence
                for r in recent_rounds
                if r.selected_proposal and not r.execution_success
            ]

            if sequence in failed_sequences:
                self.sequence_index += 1
                sequence = self.POWER_OPTIMIZATION_SEQUENCES[
                    self.sequence_index % len(self.POWER_OPTIMIZATION_SEQUENCES)
                ]

        # 预期改进（平衡策略）
        expected_improvement = {
            "area": 5.0,    # 预期面积减少 5%
            "delay": 5.0,   # 预期延迟减少 5%
            "power": 8.0,   # 预期功耗减少 8%
        }

        proposal = Proposal(
            proposal_id=self._generate_proposal_id(),
            agent_type=self.agent_type,
            abc_sequence=sequence,
            rationale=f"Power-focused optimization with balanced PPA strategy",
            expected_improvement=expected_improvement,
        )

        self.proposal_history.append(proposal)
        return proposal

    def vote_on_proposal(
        self,
        proposal: Proposal,
        current_metrics: PPAMetrics,
        state: NegotiationState,
    ) -> Vote:
        """
        对提案投票

        投票策略：
        - 综合考虑面积、延迟和功耗
        - 支持平衡优化的提案
        """
        expected_area_change = proposal.expected_improvement.get("area", 0.0)
        expected_delay_change = proposal.expected_improvement.get("delay", 0.0)
        expected_power_change = proposal.expected_improvement.get("power", 0.0)

        # 综合效用（加权平均）
        utility_score = (
            0.3 * expected_area_change +
            0.3 * expected_delay_change +
            0.4 * expected_power_change
        ) / 100.0

        # 投票决策
        if utility_score > 0.05:
            vote_type = VoteType.SUPPORT
            reasoning = f"Supports balanced PPA optimization (utility: {utility_score:.3f})"
        elif utility_score < -0.05:
            vote_type = VoteType.OPPOSE
            reasoning = f"Opposes unbalanced optimization (utility: {utility_score:.3f})"
        else:
            vote_type = VoteType.NEUTRAL
            reasoning = "Neutral on marginal PPA impact"

        vote = Vote(
            voter_type=self.agent_type,
            proposal_id=proposal.proposal_id,
            vote_type=vote_type,
            utility_score=utility_score,
            reasoning=reasoning,
        )

        self.vote_history.append(vote)
        return vote

    def calculate_utility(
        self,
        metrics: PPAMetrics,
        baseline: PPAMetrics,
    ) -> float:
        """
        计算功耗效用函数

        效用 = 0.3 * area_improvement + 0.3 * delay_improvement + 0.4 * power_improvement
        """
        area_improvement = 0.0
        if baseline.area > 0:
            area_improvement = (baseline.area - metrics.area) / baseline.area

        delay_improvement = 0.0
        if baseline.delay > 0:
            delay_improvement = (baseline.delay - metrics.delay) / baseline.delay

        power_improvement = 0.0
        if baseline.power and metrics.power and baseline.power > 0:
            power_improvement = (baseline.power - metrics.power) / baseline.power

        # 加权综合效用
        utility = (
            0.3 * area_improvement +
            0.3 * delay_improvement +
            0.4 * power_improvement
        )

        return utility
