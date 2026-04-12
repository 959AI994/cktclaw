"""
Pareto Tracker - Pareto 前沿追踪器

实时维护和追踪 Pareto 最优解集合。
"""

from typing import List, Set, Tuple
from copy import deepcopy

from .types import PPAMetrics


class ParetoTracker:
    """
    Pareto 前沿追踪器

    职责：
    1. 维护 Pareto 前沿（非支配解集合）
    2. 判断新解是否为 Pareto 最优
    3. 更新 Pareto 前沿
    4. 计算 Pareto 排名
    """

    def __init__(self):
        """初始化追踪器"""
        self.pareto_front: List[PPAMetrics] = []
        self.all_solutions: List[PPAMetrics] = []

    def add_solution(self, metrics: PPAMetrics) -> bool:
        """
        添加新解并更新 Pareto 前沿

        Args:
            metrics: 新的 PPA 指标

        Returns:
            是否为 Pareto 最优解
        """
        # 记录所有解
        self.all_solutions.append(deepcopy(metrics))

        # 检查是否被现有前沿中的解支配
        is_dominated = False
        for front_solution in self.pareto_front:
            if front_solution.dominates(metrics):
                is_dominated = True
                break

        if is_dominated:
            return False

        # 新解不被支配，加入前沿
        # 同时移除被新解支配的旧解
        new_front = []
        for front_solution in self.pareto_front:
            if not metrics.dominates(front_solution):
                new_front.append(front_solution)

        new_front.append(deepcopy(metrics))
        self.pareto_front = new_front

        return True

    def is_pareto_optimal(self, metrics: PPAMetrics) -> bool:
        """
        判断解是否为 Pareto 最优

        Args:
            metrics: PPA 指标

        Returns:
            是否为 Pareto 最优
        """
        # 检查是否被前沿中的任何解支配
        for front_solution in self.pareto_front:
            if front_solution.dominates(metrics):
                return False

        return True

    def get_pareto_front(self) -> List[PPAMetrics]:
        """
        获取当前 Pareto 前沿

        Returns:
            Pareto 前沿解集合
        """
        return deepcopy(self.pareto_front)

    def get_pareto_rank(self, metrics: PPAMetrics) -> int:
        """
        计算解的 Pareto 排名

        排名 0：Pareto 前沿（非支配解）
        排名 1：被前沿支配一次的解
        排名 2：被前沿支配两次的解
        ...

        Args:
            metrics: PPA 指标

        Returns:
            Pareto 排名
        """
        if not self.all_solutions:
            return 0

        # 使用快速非支配排序算法
        return self._fast_non_dominated_sort([metrics])[0]

    def _fast_non_dominated_sort(
        self,
        solutions: List[PPAMetrics]
    ) -> List[int]:
        """
        快速非支配排序算法

        Args:
            solutions: 解集合

        Returns:
            每个解的排名
        """
        n = len(solutions)
        ranks = [0] * n

        # 对每个解，计算被多少个解支配
        domination_count = [0] * n
        dominated_solutions = [[] for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue

                if solutions[i].dominates(solutions[j]):
                    dominated_solutions[i].append(j)
                elif solutions[j].dominates(solutions[i]):
                    domination_count[i] += 1

        # 第一层：非支配解
        current_front = []
        for i in range(n):
            if domination_count[i] == 0:
                ranks[i] = 0
                current_front.append(i)

        # 后续层
        rank = 0
        while current_front:
            next_front = []
            for i in current_front:
                for j in dominated_solutions[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        ranks[j] = rank + 1
                        next_front.append(j)

            rank += 1
            current_front = next_front

        return ranks

    def calculate_hypervolume(
        self,
        reference_point: PPAMetrics
    ) -> float:
        """
        计算 Pareto 前沿的超体积（Hypervolume）

        超体积是 Pareto 前沿质量的重要指标。

        Args:
            reference_point: 参考点（通常是最差的点）

        Returns:
            超体积值
        """
        if not self.pareto_front:
            return 0.0

        # 简化实现：2D 超体积（面积和延迟）
        # 对前沿按面积排序
        sorted_front = sorted(
            self.pareto_front,
            key=lambda m: m.area
        )

        hypervolume = 0.0
        prev_area = 0

        for solution in sorted_front:
            # 计算矩形面积
            width = solution.area - prev_area
            height = reference_point.delay - solution.delay

            if width > 0 and height > 0:
                hypervolume += width * height

            prev_area = solution.area

        return hypervolume

    def calculate_spacing(self) -> float:
        """
        计算 Pareto 前沿的间距（Spacing）

        间距衡量前沿解的分布均匀性。

        Returns:
            间距值（越小越均匀）
        """
        if len(self.pareto_front) < 2:
            return 0.0

        # 计算每个解到最近邻的距离
        distances = []
        for i, solution_i in enumerate(self.pareto_front):
            min_distance = float('inf')

            for j, solution_j in enumerate(self.pareto_front):
                if i == j:
                    continue

                # 欧氏距离（归一化）
                distance = self._euclidean_distance(solution_i, solution_j)
                min_distance = min(min_distance, distance)

            distances.append(min_distance)

        # 计算距离的标准差
        mean_distance = sum(distances) / len(distances)
        variance = sum((d - mean_distance) ** 2 for d in distances) / len(distances)
        spacing = variance ** 0.5

        return spacing

    def _euclidean_distance(
        self,
        metrics1: PPAMetrics,
        metrics2: PPAMetrics
    ) -> float:
        """
        计算两个解之间的欧氏距离

        Args:
            metrics1: 第一个解
            metrics2: 第二个解

        Returns:
            欧氏距离
        """
        # 归一化距离（假设面积和延迟的量级不同）
        area_diff = (metrics1.area - metrics2.area) / max(metrics1.area, metrics2.area, 1)
        delay_diff = (metrics1.delay - metrics2.delay) / max(metrics1.delay, metrics2.delay, 1)

        distance = (area_diff ** 2 + delay_diff ** 2) ** 0.5

        return distance

    def get_extreme_solutions(self) -> Tuple[PPAMetrics, PPAMetrics]:
        """
        获取极端解

        Returns:
            (最小面积解, 最小延迟解)
        """
        if not self.pareto_front:
            raise ValueError("Pareto front is empty")

        min_area_solution = min(self.pareto_front, key=lambda m: m.area)
        min_delay_solution = min(self.pareto_front, key=lambda m: m.delay)

        return min_area_solution, min_delay_solution

    def get_knee_point(self) -> PPAMetrics:
        """
        获取膝点（Knee Point）

        膝点是 Pareto 前沿上最平衡的解。

        Returns:
            膝点解
        """
        if not self.pareto_front:
            raise ValueError("Pareto front is empty")

        if len(self.pareto_front) == 1:
            return self.pareto_front[0]

        # 使用角度法找膝点
        # 膝点是曲线弯曲最大的点
        max_angle = -1
        knee_solution = self.pareto_front[0]

        sorted_front = sorted(
            self.pareto_front,
            key=lambda m: m.area
        )

        for i in range(1, len(sorted_front) - 1):
            prev = sorted_front[i - 1]
            curr = sorted_front[i]
            next_sol = sorted_front[i + 1]

            # 计算角度
            angle = self._calculate_angle(prev, curr, next_sol)

            if angle > max_angle:
                max_angle = angle
                knee_solution = curr

        return knee_solution

    def _calculate_angle(
        self,
        p1: PPAMetrics,
        p2: PPAMetrics,
        p3: PPAMetrics
    ) -> float:
        """
        计算三点之间的角度

        Args:
            p1: 第一个点
            p2: 中间点
            p3: 第三个点

        Returns:
            角度（弧度）
        """
        import math

        # 向量 p1->p2
        v1 = (p2.area - p1.area, p2.delay - p1.delay)

        # 向量 p2->p3
        v2 = (p3.area - p2.area, p3.delay - p2.delay)

        # 计算夹角
        dot_product = v1[0] * v2[0] + v1[1] * v2[1]
        magnitude1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
        magnitude2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        cos_angle = dot_product / (magnitude1 * magnitude2)
        cos_angle = max(-1.0, min(1.0, cos_angle))  # 限制在 [-1, 1]

        angle = math.acos(cos_angle)

        return angle

    def clear(self):
        """清空追踪器"""
        self.pareto_front.clear()
        self.all_solutions.clear()

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        if not self.pareto_front:
            return {
                "front_size": 0,
                "total_solutions": len(self.all_solutions),
            }

        min_area = min(m.area for m in self.pareto_front)
        max_area = max(m.area for m in self.pareto_front)
        min_delay = min(m.delay for m in self.pareto_front)
        max_delay = max(m.delay for m in self.pareto_front)

        return {
            "front_size": len(self.pareto_front),
            "total_solutions": len(self.all_solutions),
            "min_area": min_area,
            "max_area": max_area,
            "min_delay": min_delay,
            "max_delay": max_delay,
            "spacing": self.calculate_spacing(),
        }
