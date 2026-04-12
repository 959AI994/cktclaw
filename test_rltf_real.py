#!/usr/bin/env python3
"""
RLTF 真实 AIG 文件测试

使用真实的 AIG 文件测试完整的 RLTF 工作流。
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import os
os.chdir(project_root)

from workflows.rltf import RLTFCoordinator, RLTFConfig
from workflows.rltf.mock_generator import MockSequenceGenerator

async def test_rltf_with_real_aig():
    """使用真实 AIG 文件测试 RLTF"""

    print("=" * 70)
    print("RLTF 真实 AIG 文件测试")
    print("=" * 70)
    print()

    # 选择一个小型 AIG 文件进行测试
    aig_file = "test/aig/ADD1b.aig"

    if not Path(aig_file).exists():
        print(f"❌ AIG 文件不存在: {aig_file}")
        return False

    print(f"📁 测试文件: {aig_file}")
    print(f"📊 文件大小: {Path(aig_file).stat().st_size} bytes")
    print()

    # 配置 RLTF（使用较少的迭代次数进行快速测试）
    config = RLTFConfig(
        aig_file_path=aig_file,
        max_iterations=5,  # 只运行 5 次迭代进行快速验证
        convergence_threshold=0.01,
        enable_checkpoints=True,
        checkpoint_interval=2,
    )

    print("⚙️  RLTF 配置:")
    print(f"   - 最大迭代次数: {config.max_iterations}")
    print(f"   - 收敛阈值: {config.convergence_threshold}")
    print(f"   - ABC 超时: {config.abc_timeout}s")
    print(f"   - STA 超时: {config.sta_timeout}s")
    print()

    # 创建协调器（使用 Mock 生成器避免需要 API key）
    coordinator = RLTFCoordinator(use_mock_generator=True)

    try:
        print("🚀 开始 RLTF 优化...")
        print("-" * 70)

        # 运行 RLTF
        result = await coordinator.run(config)

        print("-" * 70)
        print()

        # 显示结果
        if result.success:
            print("✅ RLTF 优化成功完成！")
            print()
            print("📈 优化结果:")
            print(f"   - 会话 ID: {result.state.session_id}")
            print(f"   - 总迭代次数: {result.state.current_iteration}")
            print(f"   - 状态: {result.state.status.value}")
            print()

            if result.best_metrics:
                print("🏆 最佳指标:")
                print(f"   - Area: {result.best_metrics.area}")
                print(f"   - Delay: {result.best_metrics.delay:.2f} ns")
                if result.best_metrics.node_count:
                    print(f"   - Nodes: {result.best_metrics.node_count}")
                if result.best_metrics.levels:
                    print(f"   - Levels: {result.best_metrics.levels}")
                print()

            if result.improvement:
                print("📊 改进率:")
                print(f"   - Area: {result.improvement.get('area', 0):.2f}%")
                print(f"   - Delay: {result.improvement.get('delay', 0):.2f}%")
                print()

            if result.best_sequence:
                print("🔧 最佳 ABC 序列:")
                print(f"   {result.best_sequence}")
                print()

            # 显示迭代历史
            if result.state.iterations:
                print("📜 迭代历史:")
                for it in result.state.iterations:
                    status = "✅" if it.abc_success else "❌"
                    best = "🏆" if it.is_best_so_far else "  "
                    print(f"   {best} Iter {it.iteration_id}: {status} "
                          f"Reward={it.reward:.4f}, "
                          f"Area={it.metrics.area if it.metrics else 'N/A'}, "
                          f"Delay={it.metrics.delay:.2f}ns" if it.metrics else "N/A")
                print()

            # 显示统计信息
            from workflows.rltf.state import RLTFStateManager
            state_manager = RLTFStateManager()
            state_manager._state = result.state
            stats = state_manager.get_statistics()

            print("📊 统计信息:")
            print(f"   - 成功率: {stats.get('success_rate', 0)*100:.1f}%")
            print(f"   - 平均 Reward: {stats.get('average_reward', 0):.4f}")
            print(f"   - 平均执行时间: {stats.get('average_duration', 0):.2f}s")
            print()

            return True
        else:
            print("❌ RLTF 优化失败")
            if result.state.errors:
                print("\n错误信息:")
                for error in result.state.errors:
                    print(f"   - Iter {error['iteration']}: {error['error']}")
            return False

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    success = await test_rltf_with_real_aig()

    print("=" * 70)
    if success:
        print("🎉 真实 AIG 文件测试通过！")
        print()
        print("✅ RLTF 系统已完全验证，可以投入使用")
    else:
        print("⚠️  测试未完全通过，请检查错误信息")
    print("=" * 70)

    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
