"""
RLTF 性能测试

测试系统的性能和资源使用情况。
"""

import pytest
import asyncio
import time
import tempfile
from pathlib import Path
import sys
import psutil
import os

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from cktclaw.workflows.rltf.coordinator import RLTFCoordinator
from cktclaw.workflows.rltf.types import RLTFConfig, PPAMetrics, RLTFIteration
from cktclaw.workflows.rltf.state import RLTFStateManager
from cktclaw.workflows.rltf.reward import RLTFRewardCalculator
from cktclaw.workflows.rltf.persistence import RLTFPersistence
from datetime import datetime


class TestPerformance:
    """性能测试"""

    def test_state_manager_performance(self):
        """测试状态管理器性能"""
        state_manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        state_manager.initialize(config)

        # 测试添加大量迭代的性能
        start_time = time.time()

        for i in range(1, 1001):
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
            state_manager.add_iteration(iteration)

        elapsed = time.time() - start_time

        # 1000 次迭代应该在 1 秒内完成
        assert elapsed < 1.0
        assert state_manager.get_iteration_count() == 1000

        print(f"\n添加 1000 次迭代耗时: {elapsed:.3f}s")

    def test_reward_calculation_performance(self):
        """测试 Reward 计算性能"""
        calculator = RLTFRewardCalculator()
        baseline = PPAMetrics(area=1000, delay=5.0, power=10.0)
        config = RLTFConfig(aig_file_path="test.aig")

        # 测试大量 reward 计算
        start_time = time.time()

        for i in range(1000):
            current = PPAMetrics(
                area=1000 - i % 100,
                delay=5.0 - (i % 100) * 0.01,
                power=10.0 - (i % 100) * 0.01
            )
            reward = calculator.calculate(current, baseline, config)

        elapsed = time.time() - start_time

        # 1000 次计算应该在 0.5 秒内完成
        assert elapsed < 0.5

        print(f"\n1000 次 Reward 计算耗时: {elapsed:.3f}s")

    def test_pareto_rank_performance(self):
        """测试 Pareto 排名计算性能"""
        calculator = RLTFRewardCalculator()

        # 创建 100 个指标
        metrics_list = [
            PPAMetrics(
                area=1000 - i * 5,
                delay=5.0 - i * 0.02
            )
            for i in range(100)
        ]

        start_time = time.time()
        ranks = calculator.calculate_pareto_rank(metrics_list)
        elapsed = time.time() - start_time

        # 100 个指标的 Pareto 排名应该在 0.1 秒内完成
        assert elapsed < 0.1
        assert len(ranks) == 100

        print(f"\n100 个指标的 Pareto 排名计算耗时: {elapsed:.3f}s")

    @pytest.mark.asyncio
    async def test_persistence_performance(self):
        """测试持久化性能"""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = RLTFPersistence(data_dir=temp_dir)
            state_manager = RLTFStateManager()

            config = RLTFConfig(aig_file_path="test.aig")
            state = state_manager.initialize(config)

            # 添加 100 次迭代
            for i in range(1, 101):
                iteration = RLTFIteration(
                    iteration_id=i,
                    timestamp=datetime.now(),
                    abc_sequence=f"seq_{i}",
                    abc_output="output" * 100,  # 较大的输出
                    abc_success=True,
                    abc_duration=1.0,
                    reward=0.1,
                    cumulative_reward=i * 0.1,
                )
                state_manager.add_iteration(iteration)

            # 测试保存性能
            start_time = time.time()
            await persistence.save_checkpoint(state)
            save_elapsed = time.time() - start_time

            # 保存应该在 1 秒内完成
            assert save_elapsed < 1.0

            # 测试加载性能
            start_time = time.time()
            loaded_state = await persistence.load_checkpoint(state.session_id)
            load_elapsed = time.time() - start_time

            # 加载应该在 1 秒内完成
            assert load_elapsed < 1.0
            assert loaded_state is not None

            print(f"\n保存检查点耗时: {save_elapsed:.3f}s")
            print(f"加载检查点耗时: {load_elapsed:.3f}s")

    def test_memory_usage(self):
        """测试内存使用"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        state_manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        state_manager.initialize(config)

        # 添加大量迭代
        for i in range(1, 1001):
            metrics = PPAMetrics(area=1000 - i, delay=5.0 - i * 0.001)
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"strash; balance; rewrite_{i}",
                abc_output="output" * 1000,  # 较大的输出
                abc_success=True,
                abc_duration=1.0,
                metrics=metrics,
                reward=0.1,
                cumulative_reward=i * 0.1,
            )
            state_manager.add_iteration(iteration)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # 1000 次迭代的内存增长应该小于 100MB
        assert memory_increase < 100

        print(f"\n1000 次迭代的内存增长: {memory_increase:.2f} MB")

    def test_convergence_detection_performance(self):
        """测试收敛检测性能"""
        state_manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        state_manager.initialize(config)

        # 添加 100 次迭代
        for i in range(1, 101):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.15 + i * 0.001,
                cumulative_reward=i * 0.15,
            )
            state_manager.add_iteration(iteration)

        # 测试收敛检测性能
        start_time = time.time()

        for _ in range(1000):
            is_converged = state_manager.is_converged(threshold=0.01)

        elapsed = time.time() - start_time

        # 1000 次收敛检测应该在 0.1 秒内完成
        assert elapsed < 0.1

        print(f"\n1000 次收敛检测耗时: {elapsed:.3f}s")

    def test_statistics_calculation_performance(self):
        """测试统计计算性能"""
        state_manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig")
        state_manager.initialize(config)

        # 添加 1000 次迭代
        for i in range(1, 1001):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output",
                abc_success=(i % 5 != 0),
                abc_duration=1.0 + i * 0.001,
                reward=0.1 * i,
                cumulative_reward=sum(0.1 * j for j in range(1, i + 1)),
            )
            state_manager.add_iteration(iteration)

        # 测试统计计算性能
        start_time = time.time()

        for _ in range(100):
            stats = state_manager.get_statistics()

        elapsed = time.time() - start_time

        # 100 次统计计算应该在 0.5 秒内完成
        assert elapsed < 0.5

        print(f"\n100 次统计计算耗时: {elapsed:.3f}s")

    def test_serialization_performance(self):
        """测试序列化性能"""
        from cktclaw.workflows.rltf.types import RLTFState

        config = RLTFConfig(aig_file_path="test.aig")
        state = RLTFState(session_id="test", config=config)

        # 添加 100 次迭代
        for i in range(1, 101):
            metrics = PPAMetrics(area=1000 - i, delay=5.0 - i * 0.01)
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i}",
                abc_output="output" * 100,
                abc_success=True,
                abc_duration=1.0,
                metrics=metrics,
                reward=0.1,
                cumulative_reward=i * 0.1,
            )
            state.iterations.append(iteration)

        # 测试序列化性能
        start_time = time.time()

        for _ in range(100):
            data = state.to_dict()

        serialize_elapsed = time.time() - start_time

        # 测试反序列化性能
        data = state.to_dict()
        start_time = time.time()

        for _ in range(100):
            restored = RLTFState.from_dict(data)

        deserialize_elapsed = time.time() - start_time

        # 序列化和反序列化都应该在 1 秒内完成
        assert serialize_elapsed < 1.0
        assert deserialize_elapsed < 1.0

        print(f"\n100 次序列化耗时: {serialize_elapsed:.3f}s")
        print(f"100 次反序列化耗时: {deserialize_elapsed:.3f}s")

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """测试并发操作性能"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建多个并发任务
            async def create_and_save_state(session_id):
                persistence = RLTFPersistence(data_dir=temp_dir)
                state_manager = RLTFStateManager()

                config = RLTFConfig(
                    aig_file_path="test.aig",
                    session_id=session_id
                )
                state = state_manager.initialize(config)

                # 添加一些迭代
                for i in range(1, 11):
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
                    state_manager.add_iteration(iteration)

                # 保存
                await persistence.save_final_state(state)

            # 并发创建 10 个会话
            start_time = time.time()

            tasks = [
                create_and_save_state(f"rltf_concurrent_{i}")
                for i in range(10)
            ]
            await asyncio.gather(*tasks)

            elapsed = time.time() - start_time

            # 10 个并发会话应该在 2 秒内完成
            assert elapsed < 2.0

            print(f"\n10 个并发会话创建耗时: {elapsed:.3f}s")


class TestScalability:
    """可扩展性测试"""

    def test_large_iteration_count(self):
        """测试大量迭代的处理"""
        state_manager = RLTFStateManager()
        config = RLTFConfig(aig_file_path="test.aig", max_iterations=10000)
        state_manager.initialize(config)

        start_time = time.time()

        # 添加 5000 次迭代
        for i in range(1, 5001):
            iteration = RLTFIteration(
                iteration_id=i,
                timestamp=datetime.now(),
                abc_sequence=f"seq_{i % 10}",  # 重复使用序列
                abc_output="output",
                abc_success=True,
                abc_duration=1.0,
                reward=0.1,
                cumulative_reward=i * 0.1,
            )
            state_manager.add_iteration(iteration)

            # 每 1000 次检查一次性能
            if i % 1000 == 0:
                elapsed = time.time() - start_time
                print(f"\n{i} 次迭代耗时: {elapsed:.3f}s")

        total_elapsed = time.time() - start_time

        # 5000 次迭代应该在 5 秒内完成
        assert total_elapsed < 5.0
        assert state_manager.get_iteration_count() == 5000

    @pytest.mark.asyncio
    async def test_large_checkpoint_file(self):
        """测试大型检查点文件的处理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = RLTFPersistence(data_dir=temp_dir)
            state_manager = RLTFStateManager()

            config = RLTFConfig(aig_file_path="test.aig")
            state = state_manager.initialize(config)

            # 添加 1000 次迭代（较大的状态）
            for i in range(1, 1001):
                iteration = RLTFIteration(
                    iteration_id=i,
                    timestamp=datetime.now(),
                    abc_sequence=f"strash; balance; rewrite_{i}",
                    abc_output="output" * 1000,  # 大输出
                    abc_success=True,
                    abc_duration=1.0,
                    reward=0.1,
                    cumulative_reward=i * 0.1,
                )
                state_manager.add_iteration(iteration)

            # 保存大型检查点
            start_time = time.time()
            checkpoint_path = await persistence.save_checkpoint(state)
            save_elapsed = time.time() - start_time

            # 检查文件大小
            file_size = Path(checkpoint_path).stat().st_size / 1024 / 1024  # MB
            print(f"\n检查点文件大小: {file_size:.2f} MB")

            # 加载大型检查点
            start_time = time.time()
            loaded_state = await persistence.load_checkpoint(state.session_id)
            load_elapsed = time.time() - start_time

            print(f"保存大型检查点耗时: {save_elapsed:.3f}s")
            print(f"加载大型检查点耗时: {load_elapsed:.3f}s")

            # 验证数据完整性
            assert loaded_state is not None
            assert loaded_state.current_iteration == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
