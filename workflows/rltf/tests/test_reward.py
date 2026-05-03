"""
RLTF Reward Calculator 单元测试

测试 Reward 计算器的所有功能。
"""

import pytest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from cktclaw.workflows.rltf.reward import RLTFRewardCalculator
from cktclaw.workflows.rltf.types import PPAMetrics, RLTFConfig


class TestRLTFRewardCalculator:
    """测试 RLTFRewardCalculator"""

    def test_initialization(self):
        """测试初始化"""
        calculator = RLTFRewardCalculator()

        # 默认权重应该归一化为 1.0
        assert abs(calculator.area_weight + calculator.delay_weight + calculator.power_weight - 1.0) < 1e-6

    def test_custom_weights(self):
        """测试自定义权重"""
        calculator = RLTFRewardCalculator(
            area_weight=0.5,
            delay_weight=0.3,
            power_weight=0.2
        )

        assert abs(calculator.area_weight - 0.5) < 1e-6
        assert abs(calculator.delay_weight - 0.3) < 1e-6
        assert abs(calculator.power_weight - 0.2) < 1e-6

    def test_calculate_improvement(self):
        """测试改进计算"""
        baseline = PPAMetrics(area=1000, delay=5.0)
        current = PPAMetrics(area=900, delay=4.5)

        config = RLTFConfig(aig_file_path="test.aig")
        calculator = RLTFRewardCalculator()

        reward = calculator.calculate(current, baseline, config)

        # 应该是正的 reward（因为有改进）
        assert reward > 0

    def test_calculate_invalid_metrics(self):
        """解析失败的指标：不得把全 0 当作相对基线的巨大改进"""
        baseline = PPAMetrics(area=1000, delay=5.0)
        bad = PPAMetrics(area=0, delay=0.0, metrics_valid=False)
        config = RLTFConfig(aig_file_path="test.aig")
        calculator = RLTFRewardCalculator()
        assert calculator.calculate(bad, baseline, config) == -1.0

    def test_calculate_degradation(self):
        """测试退化情况"""
        baseline = PPAMetrics(area=1000, delay=5.0)
        current = PPAMetrics(area=1100, delay=5.5)  # 更差

        config = RLTFConfig(aig_file_path="test.aig")
        calculator = RLTFRewardCalculator()

        reward = calculator.calculate(current, baseline, config)

        # 应该是负的 reward（因为退化）
        assert reward < 0

    def test_calculate_with_power(self):
        """测试包含功耗的计算"""
        baseline = PPAMetrics(area=1000, delay=5.0, power=10.0)
        current = PPAMetrics(area=900, delay=4.5, power=9.0)

        config = RLTFConfig(aig_file_path="test.aig")
        calculator = RLTFRewardCalculator()

        reward = calculator.calculate(current, baseline, config)

        # 所有指标都改进，应该是正的 reward
        assert reward > 0

    def test_constraint_penalty_area(self):
        """测试面积约束惩罚"""
        baseline = PPAMetrics(area=1000, delay=5.0)
        current = PPAMetrics(area=900, delay=4.5)

        # 设置目标面积为 800（当前 900 超过了）
        config = RLTFConfig(
            aig_file_path="test.aig",
            target_area=800
        )
        calculator = RLTFRewardCalculator()

        reward = calculator.calculate(current, baseline, config)

        # 虽然有改进，但因为违反约束，reward 会被惩罚
        # 计算无约束的 reward
        config_no_constraint = RLTFConfig(aig_file_path="test.aig")
        reward_no_constraint = calculator.calculate(current, baseline, config_no_constraint)

        # 有约束的 reward 应该更小
        assert reward < reward_no_constraint

    def test_constraint_penalty_delay(self):
        """测试延迟约束惩罚"""
        baseline = PPAMetrics(area=1000, delay=5.0)
        current = PPAMetrics(area=900, delay=4.5)

        # 设置目标延迟为 4.0（当前 4.5 超过了）
        config = RLTFConfig(
            aig_file_path="test.aig",
            target_delay=4.0
        )
        calculator = RLTFRewardCalculator()

        reward = calculator.calculate(current, baseline, config)

        # 应该有惩罚
        config_no_constraint = RLTFConfig(aig_file_path="test.aig")
        reward_no_constraint = calculator.calculate(current, baseline, config_no_constraint)

        assert reward < reward_no_constraint

    def test_is_dominated_true(self):
        """测试 Pareto 支配关系（被支配）"""
        calculator = RLTFRewardCalculator()

        a = PPAMetrics(area=1000, delay=5.0)
        b = PPAMetrics(area=900, delay=4.5)  # b 在所有方面都优于 a

        assert calculator.is_dominated(a, b) is True

    def test_is_dominated_false(self):
        """测试 Pareto 支配关系（不被支配）"""
        calculator = RLTFRewardCalculator()

        a = PPAMetrics(area=900, delay=5.0)
        b = PPAMetrics(area=1000, delay=4.5)  # b 在 delay 上更好，但 area 更差

        assert calculator.is_dominated(a, b) is False

    def test_is_dominated_equal(self):
        """测试 Pareto 支配关系（相等）"""
        calculator = RLTFRewardCalculator()

        a = PPAMetrics(area=1000, delay=5.0)
        b = PPAMetrics(area=1000, delay=5.0)  # 完全相等

        assert calculator.is_dominated(a, b) is False

    def test_calculate_pareto_rank(self):
        """测试 Pareto 排名计算"""
        calculator = RLTFRewardCalculator()

        metrics_list = [
            PPAMetrics(area=1000, delay=5.0),  # 0: 被 1 和 2 支配
            PPAMetrics(area=900, delay=4.5),   # 1: Pareto 前沿
            PPAMetrics(area=950, delay=4.0),   # 2: Pareto 前沿
            PPAMetrics(area=1100, delay=5.5),  # 3: 被所有支配
        ]

        ranks = calculator.calculate_pareto_rank(metrics_list)

        # 1 和 2 应该在 Pareto 前沿（rank 0）
        assert ranks[1] == 0
        assert ranks[2] == 0

        # 0 和 3 应该有更高的 rank
        assert ranks[0] > 0
        assert ranks[3] > 0

    def test_calculate_diversity_bonus(self):
        """测试多样性奖励计算"""
        calculator = RLTFRewardCalculator()

        current = PPAMetrics(area=1000, delay=5.0)
        history = [
            PPAMetrics(area=900, delay=4.5),
            PPAMetrics(area=950, delay=4.8),
        ]

        bonus = calculator.calculate_diversity_bonus(current, history)

        # 应该有正的多样性奖励
        assert bonus >= 0

    def test_calculate_diversity_bonus_empty_history(self):
        """测试空历史的多样性奖励"""
        calculator = RLTFRewardCalculator()

        current = PPAMetrics(area=1000, delay=5.0)
        history = []

        bonus = calculator.calculate_diversity_bonus(current, history)

        # 空历史应该返回 0
        assert bonus == 0

    def test_calculate_improvement_rate(self):
        """测试改进率计算"""
        calculator = RLTFRewardCalculator()

        baseline = PPAMetrics(area=1000, delay=5.0, power=10.0)
        current = PPAMetrics(area=900, delay=4.5, power=9.0)

        improvement = calculator.calculate_improvement_rate(current, baseline)

        # 检查改进率
        assert improvement["area"] == 10.0  # (1000-900)/1000 * 100
        assert improvement["delay"] == 10.0  # (5.0-4.5)/5.0 * 100
        assert improvement["power"] == 10.0  # (10.0-9.0)/10.0 * 100

    def test_calculate_improvement_rate_negative(self):
        """测试负改进率（退化）"""
        calculator = RLTFRewardCalculator()

        baseline = PPAMetrics(area=1000, delay=5.0)
        current = PPAMetrics(area=1100, delay=5.5)  # 更差

        improvement = calculator.calculate_improvement_rate(current, baseline)

        # 应该是负值
        assert improvement["area"] < 0
        assert improvement["delay"] < 0

    def test_weighted_reward_calculation(self):
        """测试加权 Reward 计算"""
        # 创建偏向 area 的计算器
        calculator_area = RLTFRewardCalculator(
            area_weight=0.8,
            delay_weight=0.2,
            power_weight=0.0
        )

        # 创建偏向 delay 的计算器
        calculator_delay = RLTFRewardCalculator(
            area_weight=0.2,
            delay_weight=0.8,
            power_weight=0.0
        )

        baseline = PPAMetrics(area=1000, delay=5.0)

        # 场景 1: area 改进多，delay 改进少
        current1 = PPAMetrics(area=800, delay=4.9)

        config = RLTFConfig(aig_file_path="test.aig")
        reward_area1 = calculator_area.calculate(current1, baseline, config)
        reward_delay1 = calculator_delay.calculate(current1, baseline, config)

        # 偏向 area 的计算器应该给更高的 reward
        assert reward_area1 > reward_delay1

        # 场景 2: delay 改进多，area 改进少
        current2 = PPAMetrics(area=990, delay=4.0)

        reward_area2 = calculator_area.calculate(current2, baseline, config)
        reward_delay2 = calculator_delay.calculate(current2, baseline, config)

        # 偏向 delay 的计算器应该给更高的 reward
        assert reward_delay2 > reward_area2

    def test_zero_baseline_handling(self):
        """测试零基线值的处理"""
        calculator = RLTFRewardCalculator()

        # 不应该崩溃
        baseline = PPAMetrics(area=0, delay=5.0)
        current = PPAMetrics(area=100, delay=4.5)

        config = RLTFConfig(aig_file_path="test.aig")

        # 应该能正常计算（即使 area 基线为 0）
        reward = calculator.calculate(current, baseline, config)
        assert isinstance(reward, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
