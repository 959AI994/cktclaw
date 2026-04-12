"""
RLTF Types 单元测试

测试所有数据类型的创建、序列化和反序列化。
"""

import pytest
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from cktclaw.workflows.rltf.types import (
    RLTFStatus,
    PPAMetrics,
    RLTFConfig,
    RLTFIteration,
    RLTFState,
    RLTFResult,
    SequenceGenerationContext,
)


class TestPPAMetrics:
    """测试 PPAMetrics 数据类"""

    def test_create_basic_metrics(self):
        """测试创建基本指标"""
        metrics = PPAMetrics(area=1000, delay=5.2)
        assert metrics.area == 1000
        assert metrics.delay == 5.2
        assert metrics.power is None

    def test_create_full_metrics(self):
        """测试创建完整指标"""
        metrics = PPAMetrics(
            area=1000,
            delay=5.2,
            power=10.5,
            node_count=500,
            edge_count=1200,
            levels=8
        )
        assert metrics.area == 1000
        assert metrics.delay == 5.2
        assert metrics.power == 10.5
        assert metrics.node_count == 500
        assert metrics.edge_count == 1200
        assert metrics.levels == 8

    def test_to_dict(self):
        """测试转换为字典"""
        metrics = PPAMetrics(area=1000, delay=5.2, power=10.5)
        data = metrics.to_dict()

        assert data["area"] == 1000
        assert data["delay"] == 5.2
        assert data["power"] == 10.5

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "area": 1000,
            "delay": 5.2,
            "power": 10.5,
            "node_count": 500,
        }
        metrics = PPAMetrics.from_dict(data)

        assert metrics.area == 1000
        assert metrics.delay == 5.2
        assert metrics.power == 10.5
        assert metrics.node_count == 500

    def test_serialization_roundtrip(self):
        """测试序列化往返"""
        original = PPAMetrics(area=1000, delay=5.2, power=10.5)
        data = original.to_dict()
        restored = PPAMetrics.from_dict(data)

        assert restored.area == original.area
        assert restored.delay == original.delay
        assert restored.power == original.power


class TestRLTFConfig:
    """测试 RLTFConfig 配置类"""

    def test_create_minimal_config(self):
        """测试创建最小配置"""
        config = RLTFConfig(aig_file_path="test.aig")

        assert config.aig_file_path == "test.aig"
        assert config.max_iterations == 50
        assert config.llm_model == "deepseek-chat"

    def test_create_full_config(self):
        """测试创建完整配置"""
        config = RLTFConfig(
            aig_file_path="test.aig",
            max_iterations=100,
            convergence_threshold=0.005,
            target_area=800,
            target_delay=4.0,
            llm_model="gpt-4",
            temperature=0.8,
        )

        assert config.max_iterations == 100
        assert config.convergence_threshold == 0.005
        assert config.target_area == 800
        assert config.target_delay == 4.0
        assert config.llm_model == "gpt-4"
        assert config.temperature == 0.8

    def test_config_serialization(self):
        """测试配置序列化"""
        config = RLTFConfig(
            aig_file_path="test.aig",
            max_iterations=100,
            target_area=800,
        )

        data = config.to_dict()
        restored = RLTFConfig.from_dict(data)

        assert restored.aig_file_path == config.aig_file_path
        assert restored.max_iterations == config.max_iterations
        assert restored.target_area == config.target_area


class TestRLTFIteration:
    """测试 RLTFIteration 迭代记录"""

    def test_create_iteration(self):
        """测试创建迭代记录"""
        metrics = PPAMetrics(area=950, delay=4.8)
        iteration = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash; balance; rewrite",
            abc_output="test output",
            abc_success=True,
            abc_duration=2.5,
            metrics=metrics,
            reward=0.15,
            cumulative_reward=0.15,
        )

        assert iteration.iteration_id == 1
        assert iteration.abc_sequence == "strash; balance; rewrite"
        assert iteration.abc_success is True
        assert iteration.reward == 0.15
        assert iteration.metrics.area == 950

    def test_iteration_serialization(self):
        """测试迭代记录序列化"""
        metrics = PPAMetrics(area=950, delay=4.8)
        original = RLTFIteration(
            iteration_id=1,
            timestamp=datetime.now(),
            abc_sequence="strash; balance",
            abc_output="output",
            abc_success=True,
            abc_duration=2.5,
            metrics=metrics,
            reward=0.15,
            cumulative_reward=0.15,
        )

        data = original.to_dict()
        restored = RLTFIteration.from_dict(data)

        assert restored.iteration_id == original.iteration_id
        assert restored.abc_sequence == original.abc_sequence
        assert restored.reward == original.reward
        assert restored.metrics.area == original.metrics.area


class TestRLTFState:
    """测试 RLTFState 运行状态"""

    def test_create_state(self):
        """测试创建状态"""
        config = RLTFConfig(aig_file_path="test.aig")
        state = RLTFState(
            session_id="test_session",
            config=config,
            status=RLTFStatus.IDLE,
        )

        assert state.session_id == "test_session"
        assert state.status == RLTFStatus.IDLE
        assert state.current_iteration == 0
        assert len(state.iterations) == 0

    def test_state_with_iterations(self):
        """测试带迭代记录的状态"""
        config = RLTFConfig(aig_file_path="test.aig")
        state = RLTFState(
            session_id="test_session",
            config=config,
        )

        # 添加迭代
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
        state.iterations.append(iteration)
        state.current_iteration = 1

        assert len(state.iterations) == 1
        assert state.current_iteration == 1

    def test_state_serialization(self):
        """测试状态序列化"""
        config = RLTFConfig(aig_file_path="test.aig")
        original = RLTFState(
            session_id="test_session",
            config=config,
            status=RLTFStatus.RUNNING,
            current_iteration=5,
        )

        data = original.to_dict()
        restored = RLTFState.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.status == original.status
        assert restored.current_iteration == original.current_iteration


class TestRLTFResult:
    """测试 RLTFResult 最终结果"""

    def test_create_result(self):
        """测试创建结果"""
        config = RLTFConfig(aig_file_path="test.aig")
        state = RLTFState(session_id="test", config=config)

        result = RLTFResult(
            success=True,
            state=state,
            best_sequence="strash; balance; rewrite",
            improvement={"area": 10.0, "delay": 8.0},
            summary="Optimization complete",
        )

        assert result.success is True
        assert result.best_sequence == "strash; balance; rewrite"
        assert result.improvement["area"] == 10.0

    def test_result_serialization(self):
        """测试结果序列化"""
        config = RLTFConfig(aig_file_path="test.aig")
        state = RLTFState(session_id="test", config=config)

        original = RLTFResult(
            success=True,
            state=state,
            best_sequence="strash; balance",
            summary="Done",
        )

        data = original.to_dict()
        restored = RLTFResult.from_dict(data)

        assert restored.success == original.success
        assert restored.best_sequence == original.best_sequence


class TestSequenceGenerationContext:
    """测试 SequenceGenerationContext 生成上下文"""

    def test_create_context(self):
        """测试创建上下文"""
        context = SequenceGenerationContext(
            current_iteration=5,
            previous_sequences=["strash", "balance"],
            previous_rewards=[0.1, 0.15],
            best_sequence="balance",
            best_reward=0.15,
        )

        assert context.current_iteration == 5
        assert len(context.previous_sequences) == 2
        assert context.best_reward == 0.15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
