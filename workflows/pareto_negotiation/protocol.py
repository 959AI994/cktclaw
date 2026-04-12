"""
Negotiation Protocol - 协商协议状态机

管理协商流程的状态转换和协议执行。
"""

from typing import List, Optional
from datetime import datetime
from enum import Enum

from .types import (
    NegotiationStatus,
    NegotiationState,
    NegotiationRound,
    Proposal,
    Vote,
    PPAMetrics,
)
from .agents import BaseAgent
from .arbiter import NashArbiter


class ProtocolPhase(Enum):
    """协议阶段"""
    INITIALIZATION = "initialization"
    PROPOSAL_GENERATION = "proposal_generation"
    VOTING = "voting"
    ARBITRATION = "arbitration"
    EXECUTION = "execution"
    EVALUATION = "evaluation"
    CONVERGENCE_CHECK = "convergence_check"
    COMPLETION = "completion"


class NegotiationProtocol:
    """
    协商协议状态机

    管理协商流程：
    1. 初始化 → 2. 提案生成 → 3. 投票 → 4. 仲裁 → 5. 执行 → 6. 评估 → 7. 收敛检查
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        arbiter: NashArbiter,
    ):
        """
        初始化协议

        Args:
            agents: 参与协商的 Agent 列表
            arbiter: Nash 仲裁者
        """
        self.agents = agents
        self.arbiter = arbiter
        self.current_phase = ProtocolPhase.INITIALIZATION

    def start_round(self, state: NegotiationState) -> NegotiationRound:
        """
        开始新一轮协商

        Args:
            state: 协商状态

        Returns:
            新的协商轮次
        """
        round_id = state.current_round + 1
        state.current_round = round_id

        negotiation_round = NegotiationRound(
            round_id=round_id,
            timestamp=datetime.now(),
        )

        state.rounds.append(negotiation_round)
        self.current_phase = ProtocolPhase.PROPOSAL_GENERATION

        return negotiation_round

    def generate_proposals(
        self,
        state: NegotiationState,
        current_metrics: PPAMetrics,
    ) -> List[Proposal]:
        """
        生成提案阶段

        每个 Agent 生成一个提案。

        Args:
            state: 协商状态
            current_metrics: 当前 PPA 指标

        Returns:
            提案列表
        """
        if self.current_phase != ProtocolPhase.PROPOSAL_GENERATION:
            raise RuntimeError(
                f"Invalid phase: expected PROPOSAL_GENERATION, got {self.current_phase}"
            )

        proposals = []
        for agent in self.agents:
            proposal = agent.generate_proposal(state, current_metrics)
            proposals.append(proposal)

        # 记录到当前轮次
        current_round = state.rounds[-1]
        current_round.proposals = proposals

        self.current_phase = ProtocolPhase.VOTING
        return proposals

    def collect_votes(
        self,
        state: NegotiationState,
        proposals: List[Proposal],
        current_metrics: PPAMetrics,
    ) -> List[Vote]:
        """
        投票阶段

        每个 Agent 对其他 Agent 的提案投票。

        Args:
            state: 协商状态
            proposals: 提案列表
            current_metrics: 当前 PPA 指标

        Returns:
            投票列表
        """
        if self.current_phase != ProtocolPhase.VOTING:
            raise RuntimeError(
                f"Invalid phase: expected VOTING, got {self.current_phase}"
            )

        votes = []
        for agent in self.agents:
            # 对其他 Agent 的提案投票
            for proposal in proposals:
                # 不对自己的提案投票
                if proposal.agent_type == agent.agent_type:
                    continue

                vote = agent.vote_on_proposal(
                    proposal,
                    current_metrics,
                    state,
                )
                votes.append(vote)

        # 记录到当前轮次
        current_round = state.rounds[-1]
        current_round.votes = votes

        self.current_phase = ProtocolPhase.ARBITRATION
        return votes

    def arbitrate_proposals(
        self,
        state: NegotiationState,
        proposals: List[Proposal],
        votes: List[Vote],
        current_metrics: PPAMetrics,
    ) -> Optional[Proposal]:
        """
        仲裁阶段

        Nash 仲裁者选择最优提案。

        Args:
            state: 协商状态
            proposals: 提案列表
            votes: 投票列表
            current_metrics: 当前 PPA 指标

        Returns:
            选中的提案
        """
        if self.current_phase != ProtocolPhase.ARBITRATION:
            raise RuntimeError(
                f"Invalid phase: expected ARBITRATION, got {self.current_phase}"
            )

        selected_proposal, nash_score, reasoning = self.arbiter.arbitrate(
            proposals,
            votes,
            self.agents,
            current_metrics,
            state,
        )

        # 记录到当前轮次
        current_round = state.rounds[-1]
        current_round.selected_proposal = selected_proposal
        current_round.nash_equilibrium_score = nash_score
        current_round.arbiter_reasoning = reasoning

        self.current_phase = ProtocolPhase.EXECUTION
        return selected_proposal

    def record_execution_result(
        self,
        state: NegotiationState,
        success: bool,
        duration: float,
        output: str,
        resulting_metrics: Optional[PPAMetrics] = None,
    ):
        """
        记录执行结果

        Args:
            state: 协商状态
            success: 是否成功
            duration: 执行时长
            output: 执行输出
            resulting_metrics: 结果指标
        """
        if self.current_phase != ProtocolPhase.EXECUTION:
            raise RuntimeError(
                f"Invalid phase: expected EXECUTION, got {self.current_phase}"
            )

        current_round = state.rounds[-1]
        current_round.execution_success = success
        current_round.execution_duration = duration
        current_round.execution_output = output
        current_round.resulting_metrics = resulting_metrics

        self.current_phase = ProtocolPhase.EVALUATION

    def evaluate_result(
        self,
        state: NegotiationState,
        resulting_metrics: PPAMetrics,
        previous_metrics: PPAMetrics,
        is_pareto_optimal: bool,
    ):
        """
        评估结果阶段

        Args:
            state: 协商状态
            resulting_metrics: 结果指标
            previous_metrics: 之前的指标
            is_pareto_optimal: 是否 Pareto 最优
        """
        if self.current_phase != ProtocolPhase.EVALUATION:
            raise RuntimeError(
                f"Invalid phase: expected EVALUATION, got {self.current_phase}"
            )

        # 计算改进率
        improvement = {}
        if previous_metrics.area > 0:
            improvement["area"] = (
                (previous_metrics.area - resulting_metrics.area) / previous_metrics.area * 100
            )
        if previous_metrics.delay > 0:
            improvement["delay"] = (
                (previous_metrics.delay - resulting_metrics.delay) / previous_metrics.delay * 100
            )
        if previous_metrics.power and resulting_metrics.power and previous_metrics.power > 0:
            improvement["power"] = (
                (previous_metrics.power - resulting_metrics.power) / previous_metrics.power * 100
            )

        # 记录到当前轮次
        current_round = state.rounds[-1]
        current_round.is_pareto_optimal = is_pareto_optimal
        current_round.improvement_over_previous = improvement

        self.current_phase = ProtocolPhase.CONVERGENCE_CHECK

    def check_convergence(
        self,
        state: NegotiationState,
        threshold: float,
    ) -> bool:
        """
        检查是否收敛

        Args:
            state: 协商状态
            threshold: 收敛阈值

        Returns:
            是否收敛
        """
        if self.current_phase != ProtocolPhase.CONVERGENCE_CHECK:
            raise RuntimeError(
                f"Invalid phase: expected CONVERGENCE_CHECK, got {self.current_phase}"
            )

        # 需要至少 5 轮才能判断收敛
        if len(state.rounds) < 5:
            return False

        # 检查最近 5 轮的改进率
        recent_rounds = state.rounds[-5:]
        improvements = []

        for round_data in recent_rounds:
            if round_data.improvement_over_previous:
                # 计算综合改进率
                area_imp = round_data.improvement_over_previous.get("area", 0.0)
                delay_imp = round_data.improvement_over_previous.get("delay", 0.0)
                combined_imp = abs(area_imp) + abs(delay_imp)
                improvements.append(combined_imp)

        if not improvements:
            return False

        # 如果平均改进率低于阈值，认为收敛
        avg_improvement = sum(improvements) / len(improvements)
        converged = avg_improvement < threshold

        if converged:
            self.current_phase = ProtocolPhase.COMPLETION
        else:
            # 准备下一轮
            self.current_phase = ProtocolPhase.PROPOSAL_GENERATION

        return converged

    def check_termination_conditions(
        self,
        state: NegotiationState,
    ) -> tuple[bool, str]:
        """
        检查终止条件

        Args:
            state: 协商状态

        Returns:
            (是否终止, 终止原因)
        """
        # 1. 达到最大轮次
        if state.current_round >= state.config.max_rounds:
            return True, f"Reached maximum rounds ({state.config.max_rounds})"

        # 2. 达到目标约束
        if state.current_metrics:
            target_met = True
            reasons = []

            if state.config.target_area:
                if state.current_metrics.area <= state.config.target_area:
                    reasons.append(f"area <= {state.config.target_area}")
                else:
                    target_met = False

            if state.config.target_delay:
                if state.current_metrics.delay <= state.config.target_delay:
                    reasons.append(f"delay <= {state.config.target_delay}")
                else:
                    target_met = False

            if state.config.target_power and state.current_metrics.power:
                if state.current_metrics.power <= state.config.target_power:
                    reasons.append(f"power <= {state.config.target_power}")
                else:
                    target_met = False

            if target_met and reasons:
                return True, f"Target constraints met: {', '.join(reasons)}"

        # 3. 连续失败
        if len(state.rounds) >= 3:
            recent_rounds = state.rounds[-3:]
            all_failed = all(not r.execution_success for r in recent_rounds)
            if all_failed:
                return True, "Three consecutive execution failures"

        return False, ""

    def reset(self):
        """重置协议状态"""
        self.current_phase = ProtocolPhase.INITIALIZATION

    def get_phase_description(self) -> str:
        """
        获取当前阶段描述

        Returns:
            阶段描述
        """
        descriptions = {
            ProtocolPhase.INITIALIZATION: "Initializing negotiation",
            ProtocolPhase.PROPOSAL_GENERATION: "Agents generating proposals",
            ProtocolPhase.VOTING: "Agents voting on proposals",
            ProtocolPhase.ARBITRATION: "Arbiter selecting optimal proposal",
            ProtocolPhase.EXECUTION: "Executing selected proposal",
            ProtocolPhase.EVALUATION: "Evaluating execution results",
            ProtocolPhase.CONVERGENCE_CHECK: "Checking convergence",
            ProtocolPhase.COMPLETION: "Negotiation completed",
        }
        return descriptions.get(self.current_phase, "Unknown phase")
