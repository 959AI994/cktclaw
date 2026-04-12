"""
Negotiation Coordinator - 协商循环协调器

管理整个多智能体协商流程的主协调器。
"""

import asyncio
import uuid
import time
from typing import Optional
from datetime import datetime
from pathlib import Path

from .types import (
    NegotiationConfig,
    NegotiationState,
    NegotiationStatus,
    NegotiationResult,
    PPAMetrics,
    AgentType,
)
from .agents import BaseAgent, AreaAgent, DelayAgent, PowerAgent
from .arbiter import NashArbiter
from .protocol import NegotiationProtocol
from .pareto_tracker import ParetoTracker
from .persistence import NegotiationPersistence

# 导入 RLTF 的执行器（复用）
import sys
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from cktclaw.workflows.rltf.executor import RLTFExecutor


class NegotiationCoordinator:
    """
    协商循环协调器

    职责：
    1. 初始化所有 Agent 和仲裁者
    2. 管理协商协议流程
    3. 执行 ABC 优化和 PPA 评估
    4. 维护 Pareto 前沿
    5. 持久化协商历史
    """

    def __init__(self):
        """初始化协调器"""
        self.agents: list[BaseAgent] = []
        self.arbiter = NashArbiter()
        self.protocol: Optional[NegotiationProtocol] = None
        self.pareto_tracker = ParetoTracker()
        self.executor = RLTFExecutor()
        self.persistence = NegotiationPersistence()
        self.abort_event: Optional[asyncio.Event] = None

    async def run(self, config: NegotiationConfig) -> NegotiationResult:
        """
        启动协商流程

        Args:
            config: 协商配置

        Returns:
            协商结果
        """
        # 初始化状态
        state = self._initialize_state(config)
        self.abort_event = asyncio.Event()

        try:
            # 验证输入文件
            await self._validate_input(config.aig_file_path)

            # 获取初始 PPA 指标
            print("📊 获取初始 PPA 指标...")
            rltf_initial_metrics = await self.executor.get_initial_metrics(
                config.aig_file_path
            )

            # 转换为 Pareto Negotiation 的 PPAMetrics
            initial_metrics = PPAMetrics(
                area=rltf_initial_metrics.area,
                delay=rltf_initial_metrics.delay,
                power=rltf_initial_metrics.power,
                node_count=rltf_initial_metrics.node_count,
                edge_count=rltf_initial_metrics.edge_count,
                levels=rltf_initial_metrics.levels,
            )

            state.initial_metrics = initial_metrics
            state.current_metrics = initial_metrics
            self.pareto_tracker.add_solution(initial_metrics)

            print(f"   Area: {initial_metrics.area}, Delay: {initial_metrics.delay:.4f} ns")
            print()

            # 初始化 Agent
            self._initialize_agents(config)

            # 初始化协议
            self.protocol = NegotiationProtocol(self.agents, self.arbiter)

            # 主循环
            state.status = NegotiationStatus.PROPOSING
            state.start_time = datetime.now()

            print(f"🚀 开始多智能体协商 (最大轮次: {config.max_rounds})")
            print("=" * 70)

            while state.current_round < config.max_rounds:
                if self.abort_event.is_set():
                    state.status = NegotiationStatus.IDLE
                    break

                # 执行一轮协商
                await self._run_negotiation_round(state)

                # 检查终止条件
                should_terminate, reason = self.protocol.check_termination_conditions(state)
                if should_terminate:
                    print(f"\n⏹️  终止: {reason}")
                    break

                # 检查收敛
                if self.protocol.check_convergence(state, config.convergence_threshold):
                    print(f"\n✅ 收敛: 改进率低于阈值 {config.convergence_threshold}")
                    break

                # 定期保存检查点
                if (config.enable_checkpoints and
                    state.current_round % config.checkpoint_interval == 0):
                    await self.persistence.save_checkpoint(state)

            # 完成
            state.status = NegotiationStatus.COMPLETED
            state.end_time = datetime.now()
            state.total_duration = (state.end_time - state.start_time).total_seconds()

            print("=" * 70)
            print()

            result = self._build_result(state)
            await self.persistence.save_final_state(state)

            return result

        except Exception as e:
            state.status = NegotiationStatus.FAILED
            state.errors.append({
                "round": state.current_round,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            raise

    async def _run_negotiation_round(self, state: NegotiationState):
        """
        执行一轮协商

        Args:
            state: 协商状态
        """
        # 开始新轮次
        negotiation_round = self.protocol.start_round(state)
        round_id = negotiation_round.round_id

        print(f"\n🔄 Round {round_id}")
        print("-" * 70)

        # 1. 提案生成阶段
        print("📝 提案生成阶段...")
        proposals = self.protocol.generate_proposals(
            state,
            state.current_metrics,
        )

        for proposal in proposals:
            print(f"   [{proposal.agent_type.value}] {proposal.abc_sequence}")

        # 2. 投票阶段
        print("\n🗳️  投票阶段...")
        votes = self.protocol.collect_votes(
            state,
            proposals,
            state.current_metrics,
        )

        # 统计投票
        vote_summary = {}
        for proposal in proposals:
            proposal_votes = [v for v in votes if v.proposal_id == proposal.proposal_id]
            support = sum(1 for v in proposal_votes if v.vote_type.value == "support")
            oppose = sum(1 for v in proposal_votes if v.vote_type.value == "oppose")
            neutral = sum(1 for v in proposal_votes if v.vote_type.value == "neutral")
            vote_summary[proposal.agent_type.value] = f"{support}✓ {oppose}✗ {neutral}○"

        for agent_type, summary in vote_summary.items():
            print(f"   [{agent_type}] {summary}")

        # 3. 仲裁阶段
        print("\n⚖️  仲裁阶段...")
        selected_proposal = self.protocol.arbitrate_proposals(
            state,
            proposals,
            votes,
            state.current_metrics,
        )

        if not selected_proposal:
            print("   ❌ 仲裁失败，无有效提案")
            self.protocol.record_execution_result(
                state,
                success=False,
                duration=0.0,
                output="No valid proposal",
            )
            return

        print(f"   ✅ 选中: [{selected_proposal.agent_type.value}] {selected_proposal.abc_sequence}")
        print(f"   Nash 分数: {negotiation_round.nash_equilibrium_score:.4f}")

        # 4. 执行阶段
        print("\n⚙️  执行阶段...")
        start_time = time.time()

        abc_result = await self.executor.execute_abc(
            state.config.aig_file_path,
            selected_proposal.abc_sequence,
            timeout=state.config.abc_timeout,
        )

        duration = time.time() - start_time

        if not abc_result.success:
            print(f"   ❌ 执行失败: {abc_result.error}")
            self.protocol.record_execution_result(
                state,
                success=False,
                duration=duration,
                output=abc_result.output,
            )
            return

        # 提取 PPA 指标
        rltf_metrics = await self.executor.extract_metrics(abc_result)

        # 转换为 Pareto Negotiation 的 PPAMetrics（包含 dominates 方法）
        resulting_metrics = PPAMetrics(
            area=rltf_metrics.area,
            delay=rltf_metrics.delay,
            power=rltf_metrics.power,
            node_count=rltf_metrics.node_count,
            edge_count=rltf_metrics.edge_count,
            levels=rltf_metrics.levels,
        )

        print(f"   ✅ 执行成功 ({duration:.2f}s)")
        print(f"   结果: Area={resulting_metrics.area}, Delay={resulting_metrics.delay:.4f}ns")

        self.protocol.record_execution_result(
            state,
            success=True,
            duration=duration,
            output=abc_result.output,
            resulting_metrics=resulting_metrics,
        )

        # 5. 评估阶段
        print("\n📊 评估阶段...")

        # 检查是否 Pareto 最优
        is_pareto_optimal = self.pareto_tracker.add_solution(resulting_metrics)

        if is_pareto_optimal:
            print("   🏆 Pareto 最优解！")
        else:
            print("   📈 非 Pareto 最优")

        # 计算改进率
        self.protocol.evaluate_result(
            state,
            resulting_metrics,
            state.current_metrics,
            is_pareto_optimal,
        )

        improvement = negotiation_round.improvement_over_previous
        if improvement:
            area_imp = improvement.get("area", 0.0)
            delay_imp = improvement.get("delay", 0.0)
            print(f"   改进: Area {area_imp:+.2f}%, Delay {delay_imp:+.2f}%")

        # 更新当前指标
        state.current_metrics = resulting_metrics

        # 显示 Pareto 前沿统计
        pareto_stats = self.pareto_tracker.get_statistics()
        print(f"   Pareto 前沿大小: {pareto_stats['front_size']}")

    def _initialize_state(self, config: NegotiationConfig) -> NegotiationState:
        """
        初始化协商状态

        Args:
            config: 配置

        Returns:
            初始状态
        """
        session_id = config.session_id or f"nego_{uuid.uuid4().hex[:12]}"
        config.session_id = session_id

        state = NegotiationState(
            session_id=session_id,
            config=config,
        )

        return state

    def _initialize_agents(self, config: NegotiationConfig):
        """
        初始化 Agent

        Args:
            config: 配置
        """
        self.agents.clear()

        agent_map = {
            AgentType.AREA: AreaAgent,
            AgentType.DELAY: DelayAgent,
            AgentType.POWER: PowerAgent,
        }

        for agent_type in config.agents:
            agent_class = agent_map.get(agent_type)
            if agent_class:
                self.agents.append(agent_class())

    def _build_result(self, state: NegotiationState) -> NegotiationResult:
        """
        构建协商结果

        Args:
            state: 最终状态

        Returns:
            协商结果
        """
        # 统计
        total_rounds = len(state.rounds)
        successful_rounds = sum(1 for r in state.rounds if r.execution_success)
        pareto_optimal_rounds = sum(1 for r in state.rounds if r.is_pareto_optimal)

        # 改进率
        improvement = None
        if state.initial_metrics and state.current_metrics:
            improvement = {}

            # Area 改进率（避免除以零）
            if state.initial_metrics.area > 0:
                improvement["area"] = (
                    (state.initial_metrics.area - state.current_metrics.area) /
                    state.initial_metrics.area * 100
                )
            else:
                improvement["area"] = 0.0

            # Delay 改进率（避免除以零）
            if state.initial_metrics.delay > 0:
                improvement["delay"] = (
                    (state.initial_metrics.delay - state.current_metrics.delay) /
                    state.initial_metrics.delay * 100
                )
            else:
                improvement["delay"] = 0.0

        # 生成摘要
        summary = self._generate_summary(
            state,
            improvement,
            total_rounds,
            successful_rounds,
            pareto_optimal_rounds,
        )

        return NegotiationResult(
            success=state.status == NegotiationStatus.COMPLETED,
            state=state,
            final_metrics=state.current_metrics,
            pareto_front=self.pareto_tracker.get_pareto_front(),
            improvement=improvement,
            total_rounds=total_rounds,
            successful_rounds=successful_rounds,
            pareto_optimal_rounds=pareto_optimal_rounds,
            summary=summary,
        )

    def _generate_summary(
        self,
        state: NegotiationState,
        improvement: Optional[dict],
        total_rounds: int,
        successful_rounds: int,
        pareto_optimal_rounds: int,
    ) -> str:
        """
        生成摘要

        Args:
            state: 状态
            improvement: 改进率
            total_rounds: 总轮次
            successful_rounds: 成功轮次
            pareto_optimal_rounds: Pareto 最优轮次

        Returns:
            摘要文本
        """
        lines = [
            "🎉 多智能体协商完成",
            "",
            f"会话 ID: {state.session_id}",
            f"总轮次: {total_rounds}",
            f"成功轮次: {successful_rounds}",
            f"Pareto 最优轮次: {pareto_optimal_rounds}",
            f"耗时: {state.total_duration:.2f}s",
            "",
        ]

        if improvement:
            lines.append("🎯 最终改进:")
            lines.append(f"  Area: {improvement['area']:+.2f}%")
            lines.append(f"  Delay: {improvement['delay']:+.2f}%")
            lines.append("")

        # Pareto 前沿统计
        pareto_stats = self.pareto_tracker.get_statistics()
        lines.append(f"📊 Pareto 前沿: {pareto_stats['front_size']} 个解")

        if pareto_stats['front_size'] > 0:
            lines.append(f"  最小面积: {pareto_stats['min_area']}")
            lines.append(f"  最小延迟: {pareto_stats['min_delay']:.4f}ns")

        return "\n".join(lines)

    async def _validate_input(self, aig_file_path: str):
        """
        验证输入文件

        Args:
            aig_file_path: AIG 文件路径
        """
        if not Path(aig_file_path).exists():
            raise FileNotFoundError(f"AIG file not found: {aig_file_path}")

    async def pause(self):
        """暂停协商"""
        if self.abort_event:
            self.abort_event.set()
