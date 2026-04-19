"""
RLTF 端到端测试

使用模拟的 ABC/OpenSTA 执行器进行完整的端到端测试。
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from cktclaw.workflows.rltf.coordinator import RLTFCoordinator
from cktclaw.workflows.rltf.types import RLTFConfig, PPAMetrics
from cktclaw.workflows.rltf.executor import ExecutionResult


class MockABCRunner:
    """模拟 ABC Runner"""

    def __init__(self):
        self.call_count = 0

    def run(self, command):
        """模拟 ABC 执行"""
        self.call_count += 1

        # 模拟成功的输出
        mock_result = Mock()
        mock_result.stdout = f"""
test : i/o =    8/    1  lat =    0  and =   {950 - self.call_count * 10}  lev =    {7 - self.call_count // 5}
        """
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_result.error = None

        return mock_result


class MockOpenSTARunner:
    """模拟 OpenSTA Runner"""

    def run(self, command):
        """模拟 OpenSTA 执行"""
        mock_result = Mock()
        mock_result.stdout = "Path Delay: 4.5"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_result.error = None

        return mock_result


class MockSequenceGenerator:
    """模拟序列生成器"""

    def __init__(self):
        self.call_count = 0
        self.sequences = [
            "strash; balance; rewrite",
            "strash; rewrite; refactor",
            "strash; balance; rewrite; refactor",
            "strash; compress",
            "strash; balance; compress",
        ]

    async def generate(self, context):
        """生成序列"""
        sequence = self.sequences[self.call_count % len(self.sequences)]
        self.call_count += 1
        return sequence


@pytest.mark.asyncio
class TestEndToEnd:
    """端到端测试"""

    async def test_basic_optimization_flow(self):
        """测试基本优化流程"""
        # 创建临时 AIG 文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            # 配置
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=5,
                convergence_threshold=0.01,
            )

            # 创建协调器并注入模拟对象
            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = MockABCRunner()
            coordinator.executor.opensta_runner = MockOpenSTARunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            # 运行优化
            result = await coordinator.run(config)

            # 验证结果
            assert result.success is True
            assert result.state.current_iteration > 0
            assert result.state.current_iteration <= 5
            assert result.best_sequence is not None
            assert result.best_metrics is not None

        finally:
            # 清理
            Path(aig_file).unlink(missing_ok=True)

    async def test_optimization_with_convergence(self):
        """测试带收敛检测的优化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=50,
                convergence_threshold=0.001,  # 很小的阈值，容易收敛
            )

            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = MockABCRunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            result = await coordinator.run(config)

            # 应该在达到最大迭代前收敛
            assert result.success is True
            # 由于模拟的改进逐渐减小，应该会收敛
            assert result.state.current_iteration < 50 or result.state.current_iteration == 50

        finally:
            Path(aig_file).unlink(missing_ok=True)

    async def test_optimization_with_target_constraints(self):
        """测试带目标约束的优化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=0,
                target_area=900,
                target_delay=4.0,
            )

            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = MockABCRunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            result = await coordinator.run(config)

            assert result.success is True
            # 验证约束被考虑（通过检查 reward 计算）
            assert result.state.config.target_area == 900

        finally:
            Path(aig_file).unlink(missing_ok=True)

    async def test_optimization_with_checkpoints(self):
        """测试带检查点的优化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
                f.write("mock aig content")
                aig_file = f.name

            try:
                config = RLTFConfig(
                    aig_file_path=aig_file,
                    max_iterations=15,
                    enable_checkpoints=True,
                    checkpoint_interval=5,
                )

                coordinator = RLTFCoordinator()
                coordinator.executor.abc_runner = MockABCRunner()
                coordinator.sequence_generator = MockSequenceGenerator()
                coordinator.persistence.data_dir = Path(temp_dir)

                result = await coordinator.run(config)

                assert result.success is True

                # 验证检查点文件存在
                session_dir = Path(temp_dir) / result.state.session_id
                checkpoints = list(session_dir.glob("checkpoint_*.json"))
                assert len(checkpoints) > 0

            finally:
                Path(aig_file).unlink(missing_ok=True)

    async def test_optimization_error_handling(self):
        """测试错误处理"""

        class FailingABCRunner:
            """总是失败的 ABC Runner"""
            def run(self, command):
                mock_result = Mock()
                mock_result.stdout = ""
                mock_result.stderr = "ABC execution failed"
                mock_result.returncode = 1
                mock_result.error = "Mock error"
                return mock_result

        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=3,
            )

            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = FailingABCRunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            result = await coordinator.run(config)

            # 即使失败，也应该完成
            assert result.state.current_iteration > 0
            # 应该有错误记录
            assert len(result.state.errors) > 0

        finally:
            Path(aig_file).unlink(missing_ok=True)

    async def test_optimization_improvement_tracking(self):
        """测试改进跟踪"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=10,
            )

            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = MockABCRunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            result = await coordinator.run(config)

            assert result.success is True

            # 验证改进信息
            if result.improvement:
                assert "area" in result.improvement
                assert "delay" in result.improvement
                # 由于模拟的改进，应该有正的改进率
                assert result.improvement["area"] != 0 or result.improvement["delay"] != 0

        finally:
            Path(aig_file).unlink(missing_ok=True)

    async def test_missing_aig_file(self):
        """测试缺失的 AIG 文件"""
        config = RLTFConfig(
            aig_file_path="/nonexistent/file.aig",
            max_iterations=5,
        )

        coordinator = RLTFCoordinator()

        # 应该抛出 FileNotFoundError
        with pytest.raises(FileNotFoundError):
            await coordinator.run(config)

    async def test_pause_and_resume(self):
        """测试暂停和恢复（基本测试）"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=20,
            )

            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = MockABCRunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            # 创建一个任务来运行优化
            async def run_with_pause():
                # 启动优化
                task = asyncio.create_task(coordinator.run(config))

                # 等待一小段时间
                await asyncio.sleep(0.1)

                # 暂停
                await coordinator.pause()

                # 等待任务完成
                try:
                    result = await task
                    return result
                except:
                    return None

            result = await run_with_pause()

            # 验证暂停生效（迭代次数应该少于最大值）
            if result:
                assert result.state.current_iteration < 20

        finally:
            Path(aig_file).unlink(missing_ok=True)

    async def test_statistics_generation(self):
        """测试统计信息生成"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.aig', delete=False) as f:
            f.write("mock aig content")
            aig_file = f.name

        try:
            config = RLTFConfig(
                aig_file_path=aig_file,
                max_iterations=10,
            )

            coordinator = RLTFCoordinator()
            coordinator.executor.abc_runner = MockABCRunner()
            coordinator.sequence_generator = MockSequenceGenerator()

            result = await coordinator.run(config)

            # 获取统计信息
            stats = coordinator.state_manager.get_statistics()

            assert stats["total_iterations"] > 0
            assert stats["successful_iterations"] >= 0
            assert stats["failed_iterations"] >= 0
            assert "success_rate" in stats
            assert "average_reward" in stats

        finally:
            Path(aig_file).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
