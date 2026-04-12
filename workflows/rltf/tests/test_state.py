"""
RLTF State Manager 单元测试

测试状态管理器的所有功能。
"""

import pytest
from datetime import datetime
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from cktclaw.workflows.rltf.state import RLTFStateManager
from cktclaw.workflows.rltf.types import (
    RLTFConfig,
    RLTFStatus,
    RLTFIteration,
    PPAMetrics,
)


class TestRLTFStateManager:
    """测试 RLTFStateManager"""

    def test_initialize(self):
        """测试初始化状态"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")

        state = manager.initialize(config)

        assert state is not None
        assert state.session_id.startswith("rltf_")
        assert state.status == RLTFStatus.IDLE
        assert state.current_iteration == 0
        assert len(state.iterations) == 0

    def test_initialize_with_session_id(self):
        """测试使用指定会话 ID 初始化"""
        manager = RLTFStateManager()
        config = RLTFConfig(
            aig_file_path="test.aig",
            session_id="custom_session_123"
        )

        state = manager.initialize(config)

        assert state.session_id == "custom_session_123"

    def test_get_state(self):
        """测试获取状态"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")

        # 初始化前应该返回 None
        assert manager.get_state() is None

        # 初始化后应该返回状态
        state = manager.initialize(config)
        assert manager.get_state() == state

    def test_update_status(self):
        """测试更新状态"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        manager.update_status(RLTFStatus.RUNNING)
        assert manager.get_state().status == RLTFStatus.RUNNING

        manager.update_status(RLTFStatus.COMPLETED)
        assert manager.get_state().status == RLTFStatus.COMPLETED

    def test_add_iteration(self):
        """测试添加迭代记录"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        iteration = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash; balance",
            abc_output="output",
            abc_success=True,
            abc_duration=2.0,
            reward=0.1,
            cumulative_reward=0.1,
        )

        manager.add_iteration(iteration)

        state = manager.get_state()
        assert len(state.iterations) == 1
        assert state.current_iteration == 1
        assert state.iterations[0].abc_sequence == "strash; balance"

    def test_update_best(self):
        """测试更新最佳结果"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        metrics = PPAMetrics(area=900, delay=4.5)
        iteration = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash; balance",
            abc_output="output",
            abc_success=True,
            abc_duration=2.0,
            metrics=metrics,
            reward=0.15,
            cumulative_reward=0.15,
        )

        manager.update_best(iteration, metrics)

        state = manager.get_state()
        assert state.best_iteration == iteration
        assert state.best_metrics == metrics
        assert state.best_metrics.area == 900

    def test_add_error(self):
        """测试添加错误记录"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        manager.add_error(1, "Test error message")

        state = manager.get_state()
        assert len(state.errors) == 1
        assert state.errors[0]["iteration"] == 1
        assert state.errors[0]["error"] == "Test error message"

    def test_set_start_time(self):
        """测试设置开始时间"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        start_time = datetime.now()
        manager.set_start_time(start_time)

        state = manager.get_state()
        assert state.start_time == start_time

    def test_set_end_time(self):
        """测试设置结束时间并计算耗时"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        start_time = datetime.now()
        manager.set_start_time(start_time)

        # 模拟一些处理时间
        import time
        time.sleep(0.1)

        end_time = datetime.now()
        manager.set_end_time(end_time)

        state = manager.get_state()
        assert state.end_time == end_time
        assert state.total_duration is not None
        assert state.total_duration > 0

    def test_get_recent_iterations(self):
        """测试获取最近的迭代记录"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 添加 15 个迭代
        for i in range(1, 16):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.1,
                cumulative_reward=i * 0.1,
            )
            manager.add_iteration(iteration)

        # 获取最近 10 个
        recent = manager.get_recent_iterations(10)
        assert len(recent) == 10
        assert recent[0].iteration_id == 6
        assert recent[-1].iteration_id == 15

    def test_get_recent_iterations_less_than_count(self):
        """测试获取最近迭代（数量不足）"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 只添加 5 个迭代
        for i in range(1, 6):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.1,
                cumulative_reward=i * 0.1,
            )
            manager.add_iteration(iteration)

        # 请求 10 个，应该返回全部 5 个
        recent = manager.get_recent_iterations(10)
        assert len(recent) == 5

    def test_get_iteration_count(self):
        """测试获取迭代次数"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        assert manager.get_iteration_count() == 0

        # 添加迭代
        for i in range(1, 6):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.1,
                cumulative_reward=i * 0.1,
            )
            manager.add_iteration(iteration)

        assert manager.get_iteration_count() == 5

    def test_is_converged(self):
        """测试收敛检测"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 添加 10 个 reward 相近的迭代（应该收敛）
        for i in range(1, 11):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.15 + i * 0.001,  # 非常小的变化
                cumulative_reward=i * 0.15,
            )
            manager.add_iteration(iteration)

        # 应该检测到收敛
        assert manager.is_converged(threshold=0.01)

    def test_is_not_converged(self):
        """测试未收敛情况"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 添加 10 个 reward 变化较大的迭代（不应该收敛）
        for i in range(1, 11):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.1 + i * 0.05,  # 较大的变化
                cumulative_reward=i * 0.1,
            )
            manager.add_iteration(iteration)

        # 不应该检测到收敛
        assert not manager.is_converged(threshold=0.01)

    def test_get_best_sequence(self):
        """测试获取最佳序列"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 初始应该返回 None
        assert manager.get_best_sequence() is None

        # 设置最佳迭代
        metrics = PPAMetrics(area=900, delay=4.5)
        iteration = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash; balance; rewrite",
            abc_output="output",
            abc_success=True,
            abc_duration=2.0,
            metrics=metrics,
            reward=0.15,
            cumulative_reward=0.15,
        )
        manager.update_best(iteration, metrics)

        assert manager.get_best_sequence() == "strash; balance; rewrite"

    def test_get_best_metrics(self):
        """测试获取最佳指标"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 初始应该返回 None
        assert manager.get_best_metrics() is None

        # 设置最佳指标
        metrics = PPAMetrics(area=900, delay=4.5)
        iteration = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash; balance",
            abc_output="output",
            abc_success=True,
            abc_duration=2.0,
            metrics=metrics,
            reward=0.15,
            cumulative_reward=0.15,
        )
        manager.update_best(iteration, metrics)

        best_metrics = manager.get_best_metrics()
        assert best_metrics is not None
        assert best_metrics.area == 900
        assert best_metrics.delay == 4.5

    def test_get_statistics(self):
        """测试获取统计信息"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 添加一些迭代（包括成功和失败）
        for i in range(1, 11):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=(i % 3 != 0),  # 每 3 个失败一次
                abc_duration=2.0,
                reward=0.1 * i,
                cumulative_reward=sum(0.1 * j for j in range(1, i + 1)),
            )
            manager.add_iteration(iteration)

        stats = manager.get_statistics()

        assert stats["total_iterations"] == 10
        assert stats["successful_iterations"] == 7
        assert stats["failed_iterations"] == 3
        assert stats["success_rate"] == 0.7
        assert stats["average_reward"] > 0
        assert stats["average_duration"] == 2.0

    def test_reset(self):
        """测试重置状态"""
        manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        manager.initialize(config)

        # 添加一些数据
        iteration = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash",
            abc_output="output",
            abc_success=True,
            abc_duration=1.0,
            reward=0.1,
            cumulative_reward=0.1,
        )
        manager.add_iteration(iteration)

        # 重置
        manager.reset()

        # 应该返回 None
        assert manager.get_state() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
