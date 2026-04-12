"""
RLTF Coordinator - 主协调器

管理 RLTF 优化流程的完整生命周期，协调各个组件的工作。
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from .types import (
    RLTFConfig,
    RLTFState,
    RLTFResult,
    RLTFStatus,
    RLTFIteration,
    PPAMetrics,
    SequenceGenerationContext,
)
from .state import RLTFStateManager
from .reward import RLTFRewardCalculator
from .sequence_generator import RLTFSequenceGenerator
from .executor import RLTFExecutor
from .persistence import RLTFPersistence


class RLTFCoordinator:
    """
    RLTF 主协调器

    职责：
    1. 管理 RL 循环生命周期
    2. 协调 ABC、OpenSTA、LLM 调用
    3. 状态管理和持久化
    4. 错误处理和恢复
    """

    def __init__(self, use_mock_generator: bool = False):
        """初始化协调器

        Args:
            use_mock_generator: 是否使用模拟生成器（用于测试）
        """
        self.state_manager = RLTFStateManager()
        self.reward_calculator = RLTFRewardCalculator()

        # 根据参数选择生成器
        if use_mock_generator:
            from .mock_generator import MockSequenceGenerator
            self.sequence_generator = MockSequenceGenerator()
        else:
            self.sequence_generator = RLTFSequenceGenerator()

        self.executor = RLTFExecutor()
        self.persistence = RLTFPersistence()
        self.abort_event: Optional[asyncio.Event] = None

    async def run(self, config: RLTFConfig) -> RLTFResult:
        """
        启动 RLTF 优化流程

        Args:
            config: RLTF 配置

        Returns:
            优化结果
        """
        # 初始化状态
        state = self.state_manager.initialize(config)
        self.abort_event = asyncio.Event()

        try:
            # 验证输入文件
            await self._validate_input(config.aig_file_path)

            # 获取初始 PPA 指标
            print(f"📊 获取初始 PPA 指标...")
            initial_metrics = await self.executor.get_initial_metrics(
                config.aig_file_path
            )
            print(f"   Area: {initial_metrics.area}, Delay: {initial_metrics.delay:.4f} ns")

            # 主循环
            state.status = RLTFStatus.RUNNING
            state.start_time = datetime.now()
            self.state_manager.set_start_time(state.start_time)

            print(f"\n🚀 开始 RLTF 优化 (最大迭代: {config.max_iterations})")
            print("=" * 60)

            while (state.current_iteration < config.max_iterations and
                   state.status == RLTFStatus.RUNNING):

                # 检查是否被中止
                if self.abort_event.is_set():
                    state.status = RLTFStatus.PAUSED
                    print("\n⏸️  优化已暂停")
                    break

                # 执行单次迭代
                iteration = await self._run_iteration(state, initial_metrics)

                # 显示进度
                self._print_iteration_progress(iteration, state)

                # 检查收敛
                if self._check_convergence(state, config):
                    print(f"\n✅ 检测到收敛 (方差 < {config.convergence_threshold})")
                    break

                # 定期保存检查点
                if (config.enable_checkpoints and
                    state.current_iteration % config.checkpoint_interval == 0):
                    checkpoint_path = await self.persistence.save_checkpoint(state)
                    print(f"💾 检查点已保存: {Path(checkpoint_path).name}")

            # 完成
            state.status = RLTFStatus.COMPLETED
            state.end_time = datetime.now()
            self.state_manager.set_end_time(state.end_time)

            print("\n" + "=" * 60)
            print("🎉 RLTF 优化完成")

            # 构建结果
            result = self._build_result(state, initial_metrics)

            # 保存最终状态和结果
            await self.persistence.save_final_state(state)
            await self.persistence.save_result(result)

            # 显示最终统计
            self._print_final_statistics(result)

            return result

        except Exception as e:
            state.status = RLTFStatus.FAILED
            self.state_manager.add_error(state.current_iteration, str(e))
            print(f"\n❌ RLTF 优化失败: {e}")
            raise

    async def _run_iteration(
        self,
        state: RLTFState,
        initial_metrics: PPAMetrics,
    ) -> RLTFIteration:
        """
        执行单次迭代

        Args:
            state: 当前状态
            initial_metrics: 初始指标

        Returns:
            迭代记录
        """
        iteration_id = state.current_iteration + 1

        try:
            # 1. 生成 ABC 序列 (LLM)
            context = self._build_generation_context(state)
            abc_sequence = await self.sequence_generator.generate(context)

            # 2. 执行 ABC 优化
            abc_result = await self.executor.execute_abc(
                state.config.aig_file_path,
                abc_sequence,
                timeout=state.config.abc_timeout
            )

            # 3. 执行 OpenSTA 时序分析（可选）
            sta_result = None
            if abc_result.success and abc_result.output_file:
                sta_result = await self.executor.execute_opensta(
                    abc_result.output_file,
                    timeout=state.config.sta_timeout
                )

            # 4. 提取 PPA 指标
            metrics = await self.executor.extract_metrics(abc_result, sta_result)

            # 5. 计算 Reward
            reward = self.reward_calculator.calculate(
                metrics,
                initial_metrics,
                state.config
            )

            cumulative_reward = (
                state.iterations[-1].cumulative_reward if state.iterations
                else 0.0
            ) + reward

            # 6. 构建迭代记录
            iteration = RLTFIteration(
                iteration_id=iteration_id,
                timestamp=datetime.now(),
                abc_sequence=abc_sequence,
                abc_output=abc_result.output,
                abc_success=abc_result.success,
                abc_duration=abc_result.duration,
                sta_output=sta_result.output if sta_result else None,
                sta_success=sta_result.success if sta_result else None,
                sta_duration=sta_result.duration if sta_result else None,
                metrics=metrics,
                reward=reward,
                cumulative_reward=cumulative_reward,
                is_best_so_far=False,
            )

            # 7. 更新最佳结果
            if self._is_better_than_best(iteration, state):
                iteration.is_best_so_far = True
                self.state_manager.update_best(iteration, metrics)

            # 8. 记录迭代
            self.state_manager.add_iteration(iteration)

            return iteration

        except Exception as e:
            # 错误处理
            self.state_manager.add_error(iteration_id, str(e))
            print(f"⚠️  迭代 {iteration_id} 失败: {e}")

            # 创建失败的迭代记录
            iteration = RLTFIteration(
                iteration_id=iteration_id,
                timestamp=datetime.now(),
                abc_sequence="",
                abc_output="",
                abc_success=False,
                abc_duration=0.0,
                metrics=None,
                reward=-1.0,
                cumulative_reward=state.iterations[-1].cumulative_reward if state.iterations else 0.0,
            )

            self.state_manager.add_iteration(iteration)
            return iteration

    def _build_generation_context(self, state: RLTFState) -> SequenceGenerationContext:
        """
        构建序列生成上下文

        Args:
            state: 当前状态

        Returns:
            生成上下文
        """
        recent = self.state_manager.get_recent_iterations(10)

        target_metrics = None
        if (state.config.target_area or state.config.target_delay or
            state.config.target_power):
            target_metrics = {
                "area": state.config.target_area,
                "delay": state.config.target_delay,
                "power": state.config.target_power,
            }

        return SequenceGenerationContext(
            current_iteration=state.current_iteration,
            previous_sequences=[it.abc_sequence for it in recent],
            previous_rewards=[it.reward for it in recent],
            best_sequence=self.state_manager.get_best_sequence(),
            best_reward=state.best_iteration.reward if state.best_iteration else None,
            current_metrics=self.state_manager.get_best_metrics(),
            target_metrics=target_metrics,
        )

    def _check_convergence(self, state: RLTFState, config: RLTFConfig) -> bool:
        """
        检查是否收敛

        Args:
            state: 当前状态
            config: 配置

        Returns:
            是否收敛
        """
        if not config.convergence_threshold:
            return False

        return self.state_manager.is_converged(config.convergence_threshold)

    def _is_better_than_best(self, iteration: RLTFIteration, state: RLTFState) -> bool:
        """
        判断是否优于当前最佳

        Args:
            iteration: 当前迭代
            state: 当前状态

        Returns:
            是否更好
        """
        if not state.best_iteration or not iteration.metrics:
            return True

        current = iteration.metrics
        best = state.best_metrics

        if not best:
            return True

        # 多目标优化：优先 area，其次 delay
        if current.area < best.area:
            return True
        if current.area == best.area and current.delay < best.delay:
            return True

        return False

    def _build_result(self, state: RLTFState, initial_metrics: PPAMetrics) -> RLTFResult:
        """
        构建最终结果

        Args:
            state: 最终状态
            initial_metrics: 初始指标

        Returns:
            优化结果
        """
        improvement = None
        if state.best_metrics:
            improvement = self.reward_calculator.calculate_improvement_rate(
                state.best_metrics,
                initial_metrics
            )

        summary = self._generate_summary(state, improvement)

        return RLTFResult(
            success=state.status == RLTFStatus.COMPLETED,
            state=state,
            best_sequence=self.state_manager.get_best_sequence(),
            best_metrics=state.best_metrics,
            improvement=improvement,
            summary=summary,
        )

    def _generate_summary(self, state: RLTFState, improvement: Optional[Dict[str, float]]) -> str:
        """
        生成摘要

        Args:
            state: 最终状态
            improvement: 改进率

        Returns:
            摘要文本
        """
        lines = [
            f"RLTF Optimization Complete",
            f"Session: {state.session_id}",
            f"Iterations: {state.current_iteration}/{state.config.max_iterations}",
            f"Duration: {state.total_duration:.2f}s" if state.total_duration else "",
            "",
        ]

        if improvement:
            lines.append("Improvements:")
            lines.append(f"  Area: {improvement['area']:.2f}%")
            lines.append(f"  Delay: {improvement['delay']:.2f}%")
            if 'power' in improvement:
                lines.append(f"  Power: {improvement['power']:.2f}%")

        if state.errors:
            lines.append("")
            lines.append(f"Errors: {len(state.errors)}")

        return "\n".join(lines)

    def _print_iteration_progress(self, iteration: RLTFIteration, state: RLTFState) -> None:
        """打印迭代进度"""
        status_icon = "✅" if iteration.is_best_so_far else "  "
        print(f"{status_icon} Iter {iteration.iteration_id:3d} | "
              f"Reward: {iteration.reward:+.4f} | "
              f"Area: {iteration.metrics.area if iteration.metrics else 'N/A':>5} | "
              f"Delay: {iteration.metrics.delay if iteration.metrics else 0:.4f} | "
              f"Seq: {iteration.abc_sequence[:40]}...")

    def _print_final_statistics(self, result: RLTFResult) -> None:
        """打印最终统计"""
        stats = self.state_manager.get_statistics()

        print(f"\n📈 统计信息:")
        print(f"   总迭代次数: {stats['total_iterations']}")
        print(f"   成功次数: {stats['successful_iterations']}")
        print(f"   失败次数: {stats['failed_iterations']}")
        print(f"   成功率: {stats['success_rate']*100:.1f}%")
        print(f"   平均 Reward: {stats['average_reward']:.4f}")
        print(f"   最佳 Reward: {stats['best_reward']:.4f}" if stats['best_reward'] else "")

        if result.improvement:
            print(f"\n🎯 最终改进:")
            print(f"   Area: {result.improvement['area']:+.2f}%")
            print(f"   Delay: {result.improvement['delay']:+.2f}%")

        if result.best_sequence:
            print(f"\n🏆 最佳序列:")
            print(f"   {result.best_sequence}")

    async def _validate_input(self, aig_file_path: str) -> None:
        """
        验证输入文件

        Args:
            aig_file_path: AIG 文件路径
        """
        if not Path(aig_file_path).exists():
            raise FileNotFoundError(f"AIG file not found: {aig_file_path}")

    async def pause(self) -> None:
        """暂停优化"""
        if self.abort_event:
            self.abort_event.set()

    async def resume(self, session_id: str) -> RLTFResult:
        """
        恢复优化

        Args:
            session_id: 会话 ID

        Returns:
            优化结果
        """
        # 加载检查点
        state = await self.persistence.load_checkpoint(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")

        # 恢复状态
        state.status = RLTFStatus.RUNNING
        self.state_manager.set_state(state)

        # 继续运行
        return await self.run(state.config)
