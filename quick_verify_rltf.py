#!/usr/bin/env python3
"""
RLTF 快速验证脚本

快速验证 RLTF 模块的基本功能。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 切换到项目目录
import os
os.chdir(project_root)

print("=" * 60)
print("RLTF 快速验证脚本")
print("=" * 60)
print()

# 测试 1: 导入测试
print("1. 测试模块导入...")
try:
    from workflows.rltf import (
        RLTFCoordinator,
        RLTFConfig,
        RLTFStateManager,
        RLTFRewardCalculator,
        RLTFSequenceGenerator,
        RLTFExecutor,
        RLTFPersistence,
        PPAMetrics,
        RLTFStatus,
    )
    print("   ✅ 所有模块导入成功")
except Exception as e:
    print(f"   ❌ 模块导入失败: {e}")
    sys.exit(1)

# 测试 2: 类型创建测试
print("\n2. 测试类型创建...")
try:
    metrics = PPAMetrics(area=1000, delay=5.0)
    config = RLTFConfig(aig_file_path="test.aig")
    print(f"   ✅ PPAMetrics: area={metrics.area}, delay={metrics.delay}")
    print(f"   ✅ RLTFConfig: max_iterations={config.max_iterations}")
except Exception as e:
    print(f"   ❌ 类型创建失败: {e}")
    sys.exit(1)

# 测试 3: 状态管理器测试
print("\n3. 测试状态管理器...")
try:
    state_manager = RLTFStateManager()
    state = state_manager.initialize(config)
    print(f"   ✅ 状态初始化成功: session_id={state.session_id}")
    print(f"   ✅ 初始状态: {state.status.value}")
except Exception as e:
    print(f"   ❌ 状态管理器测试失败: {e}")
    sys.exit(1)

# 测试 4: Reward 计算器测试
print("\n4. 测试 Reward 计算器...")
try:
    calculator = RLTFRewardCalculator()
    baseline = PPAMetrics(area=1000, delay=5.0)
    current = PPAMetrics(area=900, delay=4.5)
    reward = calculator.calculate(current, baseline, config)
    print(f"   ✅ Reward 计算成功: {reward:.4f}")

    improvement = calculator.calculate_improvement_rate(current, baseline)
    print(f"   ✅ 改进率: Area={improvement['area']:.2f}%, Delay={improvement['delay']:.2f}%")
except Exception as e:
    print(f"   ❌ Reward 计算器测试失败: {e}")
    sys.exit(1)

# 测试 5: 序列化测试
print("\n5. 测试序列化...")
try:
    # 测试 PPAMetrics 序列化
    metrics_dict = metrics.to_dict()
    restored_metrics = PPAMetrics.from_dict(metrics_dict)
    assert restored_metrics.area == metrics.area
    print("   ✅ PPAMetrics 序列化成功")

    # 测试 RLTFConfig 序列化
    config_dict = config.to_dict()
    restored_config = RLTFConfig.from_dict(config_dict)
    assert restored_config.max_iterations == config.max_iterations
    print("   ✅ RLTFConfig 序列化成功")

    # 测试 RLTFState 序列化
    state_dict = state.to_dict()
    from workflows.rltf.types import RLTFState
    restored_state = RLTFState.from_dict(state_dict)
    assert restored_state.session_id == state.session_id
    print("   ✅ RLTFState 序列化成功")
except Exception as e:
    print(f"   ❌ 序列化测试失败: {e}")
    sys.exit(1)

# 测试 6: Pareto 支配测试
print("\n6. 测试 Pareto 支配关系...")
try:
    a = PPAMetrics(area=1000, delay=5.0)
    b = PPAMetrics(area=900, delay=4.5)
    is_dominated = calculator.is_dominated(a, b)
    print(f"   ✅ Pareto 支配判断: A 被 B 支配 = {is_dominated}")

    metrics_list = [
        PPAMetrics(area=1000, delay=5.0),
        PPAMetrics(area=900, delay=4.5),
        PPAMetrics(area=950, delay=4.0),
    ]
    ranks = calculator.calculate_pareto_rank(metrics_list)
    print(f"   ✅ Pareto 排名计算成功: {ranks}")
except Exception as e:
    print(f"   ❌ Pareto 测试失败: {e}")
    sys.exit(1)

# 测试 7: 持久化测试
print("\n7. 测试持久化...")
try:
    import tempfile
    import asyncio

    async def test_persistence():
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = RLTFPersistence(data_dir=temp_dir)

            # 保存状态
            await persistence.save_final_state(state)
            print("   ✅ 状态保存成功")

            # 加载状态
            loaded = await persistence.load_state(state.session_id)
            assert loaded is not None
            print("   ✅ 状态加载成功")

            # 列出会话
            sessions = persistence.list_sessions()
            print(f"   ✅ 会话列表: {len(sessions)} 个会话")

    asyncio.run(test_persistence())
except Exception as e:
    print(f"   ❌ 持久化测试失败: {e}")
    sys.exit(1)

# 测试 8: 统计信息测试
print("\n8. 测试统计信息...")
try:
    from workflows.rltf.types import RLTFIteration
    from datetime import datetime

    # 添加一些迭代
    for i in range(1, 6):
        iteration = RLTFIteration(
            iteration_id=i,
            timestamp=datetime.now(),
            abc_sequence=f"seq_{i}",
            abc_output="output",
            abc_success=(i % 2 == 0),
            abc_duration=1.0,
            reward=0.1 * i,
            cumulative_reward=sum(0.1 * j for j in range(1, i + 1)),
        )
        state_manager.add_iteration(iteration)

    stats = state_manager.get_statistics()
    print(f"   ✅ 总迭代: {stats['total_iterations']}")
    print(f"   ✅ 成功率: {stats['success_rate']*100:.1f}%")
    print(f"   ✅ 平均 Reward: {stats['average_reward']:.4f}")
except Exception as e:
    print(f"   ❌ 统计信息测试失败: {e}")
    sys.exit(1)

# 测试 9: 收敛检测测试
print("\n9. 测试收敛检测...")
try:
    # 添加更多相似的迭代
    for i in range(6, 16):
        iteration = RLTFIteration(
            iteration_id=i,
            timestamp=datetime.now(),
            abc_sequence=f"seq_{i}",
            abc_output="output",
            abc_success=True,
            abc_duration=1.0,
            reward=0.15 + i * 0.001,  # 非常小的变化
            cumulative_reward=sum(0.15 + j * 0.001 for j in range(1, i + 1)),
        )
        state_manager.add_iteration(iteration)

    is_converged = state_manager.is_converged(threshold=0.01)
    print(f"   ✅ 收敛检测: {is_converged}")
except Exception as e:
    print(f"   ❌ 收敛检测测试失败: {e}")
    sys.exit(1)

# 测试 10: Skill 注册测试
print("\n10. 测试 Skill 注册...")
try:
    from skills.rltf_skill import RLTF_SKILL
    print(f"   ✅ Skill 名称: {RLTF_SKILL.name}")
    print(f"   ✅ Skill 类型: {RLTF_SKILL.skill_type}")
    print(f"   ✅ 用户可调用: {RLTF_SKILL.user_invocable}")
    print(f"   ✅ 别名: {', '.join(RLTF_SKILL.aliases)}")
except Exception as e:
    print(f"   ❌ Skill 注册测试失败: {e}")
    sys.exit(1)

# 总结
print("\n" + "=" * 60)
print("✅ 所有验证测试通过！")
print("=" * 60)
print()
print("RLTF 模块已准备就绪，可以使用以下方式调用：")
print()
print("1. CLI 命令:")
print("   > /rltf test.aig 50")
print()
print("2. Python API:")
print("   from workflows.rltf import RLTFCoordinator, RLTFConfig")
print("   config = RLTFConfig(aig_file_path='test.aig', max_iterations=50)")
print("   coordinator = RLTFCoordinator()")
print("   result = await coordinator.run(config)")
print()
print("3. 运行完整测试:")
print("   bash run_rltf_tests.sh")
print()
