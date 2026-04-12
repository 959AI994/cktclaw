"""
RLTF Reward Calculator - Reward 计算器

基于 PPA 指标计算 Reward，支持多目标优化和约束惩罚。
"""

from typing import Optional, Dict
from .types import PPAMetrics, RLTFConfig


class RLTFRewardCalculator:
    """
    RLTF Reward 计算器

    根据 PPA 指标计算 Reward，支持：
    - 多目标优化（area, delay, power）
    - 目标约束惩罚
    - Pareto 支配关系判断
    """

    def __init__(
        self,
        area_weight: float = 0.4,
        delay_weight: float = 0.4,
        power_weight: float = 0.2,
    ):
        """
        初始化 Reward 计算器

        Args:
            area_weight: 面积权重
            delay_weight: 延迟权重
            power_weight: 功耗权重
        """
        # 确保权重和为 1.0
        total = area_weight + delay_weight + power_weight
        self.area_weight = area_weight / total
        self.delay_weight = delay_weight / total
        self.power_weight = power_weight / total

    def calculate(
        self,
        current: PPAMetrics,
        baseline: PPAMetrics,
        config: RLTFConfig,
    ) -> float:
        """
        计算 Reward

        策略：
        1. 归一化各指标的改进率到 [0, 1]
        2. 加权求和
        3. 考虑目标约束惩罚

        Args:
            current: 当前 PPA 指标
            baseline: 基线 PPA 指标（初始值）
            config: RLTF 配置（包含目标约束）

        Returns:
            Reward 值（可能为负）
        """
        # 计算改进率（正值表示改进）
        area_improvement = self._calculate_improvement(
            baseline.area, current.area
        )
        delay_improvement = self._calculate_improvement(
            baseline.delay, current.delay
        )

        # 功耗改进（如果有）
        power_improvement = 0.0
        if baseline.power is not None and current.power is not None:
            power_improvement = self._calculate_improvement(
                baseline.power, current.power
            )

        # 加权求和
        reward = (
            self.area_weight * area_improvement +
            self.delay_weight * delay_improvement +
            self.power_weight * power_improvement
        )

        # 约束惩罚
        penalty = self._calculate_constraint_penalty(current, config)
        reward -= penalty

        return reward

    def _calculate_improvement(self, baseline: float, current: float) -> float:
        """
        计算改进率

        Args:
            baseline: 基线值
            current: 当前值

        Returns:
            改进率（正值表示改进，负值表示退化）
        """
        if baseline == 0:
            return 0.0

        improvement = (baseline - current) / baseline
        return improvement

    def _calculate_constraint_penalty(
        self,
        current: PPAMetrics,
        config: RLTFConfig,
    ) -> float:
        """
        计算约束惩罚

        如果违反目标约束，施加惩罚。

        Args:
            current: 当前 PPA 指标
            config: RLTF 配置

        Returns:
            惩罚值（非负）
        """
        penalty = 0.0

        # Area 约束
        if config.target_area is not None and current.area > config.target_area:
            violation_ratio = (current.area - config.target_area) / config.target_area
            penalty += 0.5 * violation_ratio

        # Delay 约束
        if config.target_delay is not None and current.delay > config.target_delay:
            violation_ratio = (current.delay - config.target_delay) / config.target_delay
            penalty += 0.5 * violation_ratio

        # Power 约束
        if (config.target_power is not None and
            current.power is not None and
            current.power > config.target_power):
            violation_ratio = (current.power - config.target_power) / config.target_power
            penalty += 0.3 * violation_ratio

        return penalty

    def is_dominated(self, a: PPAMetrics, b: PPAMetrics) -> bool:
        """
        判断 a 是否被 b Pareto 支配

        如果 b 在所有目标上都不差于 a，且至少在一个目标上严格优于 a，
        则 a 被 b 支配。

        Args:
            a: 指标 A
            b: 指标 B

        Returns:
            True 如果 a 被 b 支配
        """
        # b 在所有目标上都不差于 a
        not_worse = (
            b.area <= a.area and
            b.delay <= a.delay and
            (a.power is None or b.power is None or b.power <= a.power)
        )

        # b 至少在一个目标上严格优于 a
        strictly_better = (
            b.area < a.area or
            b.delay < a.delay or
            (a.power is not None and b.power is not None and b.power < a.power)
        )

        return not_worse and strictly_better

    def calculate_pareto_rank(self, metrics_list: list[PPAMetrics]) -> Dict[int, int]:
        """
        计算 Pareto 排名

        返回每个指标在 Pareto 前沿中的排名。
        排名 0 表示在 Pareto 前沿上（未被任何其他解支配）。

        Args:
            metrics_list: PPA 指标列表

        Returns:
            索引到排名的映射
        """
        n = len(metrics_list)
        domination_count = [0] * n  # 被多少个解支配
        dominated_solutions = [[] for _ in range(n)]  # 支配哪些解

        # 计算支配关系
        for i in range(n):
            for j in range(n):
                if i != j:
                    if self.is_dominated(metrics_list[i], metrics_list[j]):
                        domination_count[i] += 1
                        dominated_solutions[j].append(i)

        # 分配排名
        ranks = {}
        current_rank = 0
        remaining = set(range(n))

        while remaining:
            # 找到当前排名的解（未被剩余解支配）
            current_front = [
                i for i in remaining
                if domination_count[i] == 0
            ]

            if not current_front:
                # 如果没有找到，说明有循环支配，将剩余的都分配到当前排名
                current_front = list(remaining)

            for i in current_front:
                ranks[i] = current_rank
                remaining.remove(i)

                # 更新被该解支配的解的计数
                for j in dominated_solutions[i]:
                    if j in remaining:
                        domination_count[j] -= 1

            current_rank += 1

        return ranks

    def calculate_diversity_bonus(
        self,
        current: PPAMetrics,
        history: list[PPAMetrics],
        diversity_weight: float = 0.1,
    ) -> float:
        """
        计算多样性奖励

        鼓励探索不同的解空间区域。

        Args:
            current: 当前指标
            history: 历史指标列表
            diversity_weight: 多样性权重

        Returns:
            多样性奖励（非负）
        """
        if not history:
            return 0.0

        # 计算与历史解的最小距离
        min_distance = float('inf')
        for hist in history:
            distance = self._calculate_distance(current, hist)
            min_distance = min(min_distance, distance)

        # 距离越大，奖励越高
        diversity_bonus = diversity_weight * min_distance
        return diversity_bonus

    def _calculate_distance(self, a: PPAMetrics, b: PPAMetrics) -> float:
        """
        计算两个 PPA 指标之间的归一化欧氏距离

        Args:
            a: 指标 A
            b: 指标 B

        Returns:
            归一化距离
        """
        # 归一化差异
        area_diff = abs(a.area - b.area) / max(a.area, b.area, 1)
        delay_diff = abs(a.delay - b.delay) / max(a.delay, b.delay, 1e-6)

        power_diff = 0.0
        if a.power is not None and b.power is not None:
            power_diff = abs(a.power - b.power) / max(a.power, b.power, 1e-6)

        # 欧氏距离
        distance = (
            area_diff ** 2 +
            delay_diff ** 2 +
            power_diff ** 2
        ) ** 0.5

        return distance

    def calculate_improvement_rate(
        self,
        current: PPAMetrics,
        baseline: PPAMetrics,
    ) -> Dict[str, float]:
        """
        计算各指标的改进率（百分比）

        Args:
            current: 当前指标
            baseline: 基线指标

        Returns:
            各指标的改进率字典
        """
        improvement = {
            "area": self._calculate_improvement(baseline.area, current.area) * 100,
            "delay": self._calculate_improvement(baseline.delay, current.delay) * 100,
        }

        if baseline.power is not None and current.power is not None:
            improvement["power"] = self._calculate_improvement(
                baseline.power, current.power
            ) * 100

        return improvement
