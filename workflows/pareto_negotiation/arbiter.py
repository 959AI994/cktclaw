"""
Nash Equilibrium Arbiter - Nash 均衡仲裁者

基于博弈论的 Nash 均衡理论，仲裁多个 Agent 的提案。
"""

from typing import List, Dict, Tuple, Optional
import math

from .types import (
    Proposal,
    Vote,
    VoteType,
    PPAMetrics,
    NegotiationState,
    AgentType,
)
from .agents import BaseAgent


class NashArbiter:
    """
    Nash 均衡仲裁者

    职责：
    1. 收集所有 Agent 的提案和投票
    2. 计算每个提案的 Nash 均衡分数
    3. 选择最优提案
    4. 提供仲裁理由
    """

    def __init__(self, epsilon: float = 0.1):
        """
        初始化仲裁者

        Args:
            epsilon: Nash 均衡容差
        """
        self.epsilon = epsilon

    def arbitrate(
        self,
        proposals: List[Proposal],
        votes: List[Vote],
        agents: List[BaseAgent],
        current_metrics: PPAMetrics,
        state: NegotiationState,
    ) -> Tuple[Optional[Proposal], float, str]:
        """
        仲裁提案

        Args:
            proposals: 所有提案
            votes: 所有投票
            agents: 所有 Agent
            current_metrics: 当前 PPA 指标
            state: 协商状态

        Returns:
            (选中的提案, Nash 均衡分数, 仲裁理由)
        """
        if not proposals:
            return None, 0.0, "No proposals to arbitrate"

        # 计算每个提案的 Nash 均衡分数
        proposal_scores = []
        for proposal in proposals:
            score = self._calculate_nash_score(
                proposal,
                votes,
                agents,
                current_metrics,
            )
            proposal_scores.append((proposal, score))

        # 按分数排序
        proposal_scores.sort(key=lambda x: x[1], reverse=True)

        # 选择最高分的提案
        best_proposal, best_score = proposal_scores[0]

        # 生成仲裁理由
        reasoning = self._generate_reasoning(
            best_proposal,
            best_score,
            proposal_scores,
            votes,
        )

        return best_proposal, best_score, reasoning

    def _calculate_nash_score(
        self,
        proposal: Proposal,
        votes: List[Vote],
        agents: List[BaseAgent],
        current_metrics: PPAMetrics,
    ) -> float:
        """
        计算提案的 Nash 均衡分数

        Nash 均衡分数 = 所有 Agent 效用的几何平均
        这确保了公平性：任何一个 Agent 的效用过低都会拉低总分。

        Args:
            proposal: 提案
            votes: 所有投票
            agents: 所有 Agent
            current_metrics: 当前指标

        Returns:
            Nash 均衡分数
        """
        # 获取该提案的所有投票
        proposal_votes = [
            v for v in votes
            if v.proposal_id == proposal.proposal_id
        ]

        if not proposal_votes:
            # 如果没有投票，使用默认效用
            return 0.0

        # 收集所有 Agent 的效用分数
        utilities = []
        for vote in proposal_votes:
            # 将效用分数归一化到 [0, 1]
            # 并加上一个小的正数避免零值
            normalized_utility = max(0.0, vote.utility_score) + self.epsilon
            utilities.append(normalized_utility)

        # 计算几何平均（Nash 乘积）
        # Nash Score = (u1 * u2 * ... * un)^(1/n)
        if not utilities:
            return 0.0

        # 使用对数避免数值溢出
        log_sum = sum(math.log(u) for u in utilities)
        nash_score = math.exp(log_sum / len(utilities))

        return nash_score

    def _generate_reasoning(
        self,
        selected_proposal: Proposal,
        selected_score: float,
        all_scores: List[Tuple[Proposal, float]],
        votes: List[Vote],
    ) -> str:
        """
        生成仲裁理由

        Args:
            selected_proposal: 选中的提案
            selected_score: 选中提案的分数
            all_scores: 所有提案及其分数
            votes: 所有投票

        Returns:
            仲裁理由
        """
        lines = []

        # 基本信息
        lines.append(f"Selected proposal from {selected_proposal.agent_type.value} agent")
        lines.append(f"Nash equilibrium score: {selected_score:.4f}")
        lines.append("")

        # 提案详情
        lines.append(f"Proposal: {selected_proposal.abc_sequence}")
        lines.append(f"Rationale: {selected_proposal.rationale}")
        lines.append("")

        # 投票统计
        proposal_votes = [
            v for v in votes
            if v.proposal_id == selected_proposal.proposal_id
        ]

        support_count = sum(1 for v in proposal_votes if v.vote_type == VoteType.SUPPORT)
        oppose_count = sum(1 for v in proposal_votes if v.vote_type == VoteType.OPPOSE)
        neutral_count = sum(1 for v in proposal_votes if v.vote_type == VoteType.NEUTRAL)

        lines.append(f"Voting results: {support_count} support, {oppose_count} oppose, {neutral_count} neutral")
        lines.append("")

        # 与其他提案的比较
        if len(all_scores) > 1:
            lines.append("Comparison with other proposals:")
            for i, (proposal, score) in enumerate(all_scores[:3]):  # 只显示前 3 个
                if proposal.proposal_id == selected_proposal.proposal_id:
                    continue
                lines.append(
                    f"  - {proposal.agent_type.value}: {score:.4f} "
                    f"({proposal.abc_sequence[:30]}...)"
                )

        return "\n".join(lines)

    def check_nash_equilibrium(
        self,
        proposals: List[Proposal],
        votes: List[Vote],
        agents: List[BaseAgent],
        current_metrics: PPAMetrics,
    ) -> bool:
        """
        检查是否达到 Nash 均衡

        Nash 均衡条件：
        没有任何 Agent 可以通过单方面改变策略来提高自己的效用。

        Args:
            proposals: 所有提案
            votes: 所有投票
            agents: 所有 Agent
            current_metrics: 当前指标

        Returns:
            是否达到 Nash 均衡
        """
        # 简化实现：检查是否所有提案的分数都很接近
        scores = []
        for proposal in proposals:
            score = self._calculate_nash_score(
                proposal,
                votes,
                agents,
                current_metrics,
            )
            scores.append(score)

        if not scores:
            return False

        # 计算分数的方差
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)

        # 如果方差很小，认为达到了均衡
        return variance < self.epsilon

    def calculate_social_welfare(
        self,
        proposal: Proposal,
        votes: List[Vote],
    ) -> float:
        """
        计算社会福利（所有 Agent 效用之和）

        Args:
            proposal: 提案
            votes: 投票

        Returns:
            社会福利值
        """
        proposal_votes = [
            v for v in votes
            if v.proposal_id == proposal.proposal_id
        ]

        if not proposal_votes:
            return 0.0

        # 社会福利 = 所有效用之和
        social_welfare = sum(v.utility_score for v in proposal_votes)

        return social_welfare

    def calculate_fairness_index(
        self,
        proposal: Proposal,
        votes: List[Vote],
    ) -> float:
        """
        计算公平性指数（Jain's Fairness Index）

        公平性指数 = (sum(u_i))^2 / (n * sum(u_i^2))
        范围 [0, 1]，越接近 1 越公平。

        Args:
            proposal: 提案
            votes: 投票

        Returns:
            公平性指数
        """
        proposal_votes = [
            v for v in votes
            if v.proposal_id == proposal.proposal_id
        ]

        if not proposal_votes:
            return 0.0

        utilities = [v.utility_score for v in proposal_votes]
        n = len(utilities)

        if n == 0:
            return 0.0

        sum_u = sum(utilities)
        sum_u_squared = sum(u ** 2 for u in utilities)

        if sum_u_squared == 0:
            return 0.0

        fairness = (sum_u ** 2) / (n * sum_u_squared)

        return fairness

    def detect_dominant_strategy(
        self,
        proposals: List[Proposal],
        votes: List[Vote],
        agents: List[BaseAgent],
        current_metrics: PPAMetrics,
    ) -> Optional[Proposal]:
        """
        检测是否存在占优策略

        占优策略：对所有 Agent 都是最优的策略。

        Args:
            proposals: 所有提案
            votes: 所有投票
            agents: 所有 Agent
            current_metrics: 当前指标

        Returns:
            占优策略提案（如果存在）
        """
        if not proposals:
            return None

        # 对每个提案，检查是否所有 Agent 都支持
        for proposal in proposals:
            proposal_votes = [
                v for v in votes
                if v.proposal_id == proposal.proposal_id
            ]

            # 如果所有投票都是支持，则为占优策略
            if all(v.vote_type == VoteType.SUPPORT for v in proposal_votes):
                return proposal

        return None

    def calculate_pareto_efficiency(
        self,
        proposal: Proposal,
        votes: List[Vote],
    ) -> float:
        """
        计算 Pareto 效率

        Pareto 效率：无法在不损害任何 Agent 的情况下改善其他 Agent。

        Args:
            proposal: 提案
            votes: 投票

        Returns:
            Pareto 效率分数 [0, 1]
        """
        proposal_votes = [
            v for v in votes
            if v.proposal_id == proposal.proposal_id
        ]

        if not proposal_votes:
            return 0.0

        # 简化实现：如果没有 Agent 反对，则认为是 Pareto 有效的
        oppose_count = sum(1 for v in proposal_votes if v.vote_type == VoteType.OPPOSE)

        if oppose_count == 0:
            return 1.0
        else:
            # 反对的 Agent 越少，Pareto 效率越高
            return 1.0 - (oppose_count / len(proposal_votes))
