"""
RLTF State Manager - 状态管理器

负责管理 RLTF 优化流程的状态，包括初始化、更新和查询。
"""

import uuid
from typing import Optional
from datetime import datetime

from .types import RLTFState, RLTFConfig, RLTFStatus, RLTFIteration, PPAMetrics


class RLTFStateManager:
    """
    RLTF 状态管理器

    提供状态的创建、更新和查询功能。
    """

    def __init__(self):
        self._state: Optional[RLTFState] = None

    def initialize(self, config: RLTFConfig) -> RLTFState:
        """
        初始化新的 RLTF 状态

        Args:
            config: RLTF 配置

        Returns:
            初始化的状态对象
        """
        session_id = config.session_id or self._generate_session_id()

        self._state = RLTFState(
            session_id=session_id,
            config=config,
            status=RLTFStatus.IDLE,
            current_iteration=0,
            iterations=[],
            best_iteration=None,
            best_metrics=None,
            start_time=None,
            end_time=None,
            total_duration=None,
            errors=[],
        )

        return self._state

    def get_state(self) -> Optional[RLTFState]:
        """
        获取当前状态

        Returns:
            当前状态对象，如果未初始化则返回 None
        """
        return self._state

    def set_state(self, state: RLTFState) -> None:
        """
        设置状态（用于恢复会话）

        Args:
            state: 要设置的状态对象
        """
        self._state = state

    def update_status(self, status: RLTFStatus) -> None:
        """
        更新运行状态

        Args:
            status: 新的状态
        """
        if self._state:
            self._state.status = status

    def add_iteration(self, iteration: RLTFIteration) -> None:
        """
        添加迭代记录

        Args:
            iteration: 迭代记录
        """
        if self._state:
            self._state.iterations.append(iteration)
            self._state.current_iteration = iteration.iteration_id

    def update_best(self, iteration: RLTFIteration, metrics: PPAMetrics) -> None:
        """
        更新最佳结果

        Args:
            iteration: 最佳迭代
            metrics: 最佳指标
        """
        if self._state:
            self._state.best_iteration = iteration
            self._state.best_metrics = metrics

    def add_error(self, iteration: int, error: str) -> None:
        """
        添加错误记录

        Args:
            iteration: 发生错误的迭代次数
            error: 错误信息
        """
        if self._state:
            self._state.errors.append({
                "iteration": iteration,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            })

    def set_start_time(self, start_time: datetime) -> None:
        """
        设置开始时间

        Args:
            start_time: 开始时间
        """
        if self._state:
            self._state.start_time = start_time

    def set_end_time(self, end_time: datetime) -> None:
        """
        设置结束时间并计算总耗时

        Args:
            end_time: 结束时间
        """
        if self._state and self._state.start_time:
            self._state.end_time = end_time
            self._state.total_duration = (
                end_time - self._state.start_time
            ).total_seconds()

    def get_recent_iterations(self, count: int = 10) -> list[RLTFIteration]:
        """
        获取最近的迭代记录

        Args:
            count: 返回的记录数量

        Returns:
            最近的迭代记录列表
        """
        if not self._state:
            return []

        return self._state.iterations[-count:] if len(self._state.iterations) >= count else self._state.iterations

    def get_iteration_count(self) -> int:
        """
        获取当前迭代次数

        Returns:
            迭代次数
        """
        return self._state.current_iteration if self._state else 0

    def is_converged(self, threshold: float) -> bool:
        """
        检查是否收敛

        Args:
            threshold: 收敛阈值

        Returns:
            是否收敛
        """
        if not self._state or len(self._state.iterations) < 10:
            return False

        recent_rewards = [it.reward for it in self._state.iterations[-10:]]
        mean = sum(recent_rewards) / len(recent_rewards)
        variance = sum((r - mean) ** 2 for r in recent_rewards) / len(recent_rewards)

        return variance < threshold

    def get_best_sequence(self) -> Optional[str]:
        """
        获取当前最佳序列

        Returns:
            最佳 ABC 序列，如果不存在则返回 None
        """
        if self._state and self._state.best_iteration:
            return self._state.best_iteration.abc_sequence
        return None

    def get_best_metrics(self) -> Optional[PPAMetrics]:
        """
        获取当前最佳指标

        Returns:
            最佳 PPA 指标，如果不存在则返回 None
        """
        return self._state.best_metrics if self._state else None

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            包含各种统计数据的字典
        """
        if not self._state:
            return {}

        successful_iterations = sum(1 for it in self._state.iterations if it.abc_success)
        failed_iterations = len(self._state.iterations) - successful_iterations

        avg_reward = (
            sum(it.reward for it in self._state.iterations) / len(self._state.iterations)
            if self._state.iterations else 0.0
        )

        avg_duration = (
            sum(it.abc_duration for it in self._state.iterations) / len(self._state.iterations)
            if self._state.iterations else 0.0
        )

        return {
            "total_iterations": len(self._state.iterations),
            "successful_iterations": successful_iterations,
            "failed_iterations": failed_iterations,
            "success_rate": successful_iterations / len(self._state.iterations) if self._state.iterations else 0.0,
            "average_reward": avg_reward,
            "average_duration": avg_duration,
            "best_reward": self._state.best_iteration.reward if self._state.best_iteration else None,
            "cumulative_reward": self._state.iterations[-1].cumulative_reward if self._state.iterations else 0.0,
            "error_count": len(self._state.errors),
        }

    def reset(self) -> None:
        """重置状态（用于测试）"""
        self._state = None

    @staticmethod
    def _generate_session_id() -> str:
        """
        生成唯一的会话 ID

        Returns:
            UUID 格式的会话 ID
        """
        return f"rltf_{uuid.uuid4().hex[:12]}"
