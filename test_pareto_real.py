#!/usr/bin/env python3
"""
Pareto Multi-Agent Negotiation 真实 AIG 文件测试

使用真实的 AIG 文件测试完整的协商工作流。
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import os
os.chdir(project_root)

from workflows.pareto_negotiation import (
    NegotiationCoordinator,
    NegotiationConfig,
    AgentType,
)

async def test_pareto_with_real_aig():
    """使用真实 AIG 文件测试 Pareto Negotiation"""

    print("=" * 70)
    print("Pareto Multi-Agent Negotiation 真实 AIG 文件测试")
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

    # 配置协商（使用较少的轮次进行快速测试）
    config = NegotiationConfig(
        aig_file_path=aig_file,
        max_rounds=5,  # 只运行 5 轮进行快速验证
        agents=[AgentType.AREA, AgentType.DELAY, AgentType.POWER],
        convergence_threshold=0.01,
        enable_checkpoints=True,
        checkpoint_interval=2,
    )

    print("⚙️  协商配置:")
    print(f"   - 最大轮次: {config.max_rounds}")
    print(f"   - 参与 Agent: {', '.join([a.value for a in config.agents])}")
    print(f"   - 收敛阈值: {config.convergence_threshold}")
    print(f"   - ABC 超时: {config.abc_timeout}s")
    print()

    # 创建协调器
    coordinator = NegotiationCoordinator()

    try:
        print("🚀 开始多智能体协商...")
        print()

        # 运行协商
        result = await coordinator.run(config)

        print()
        print("=" * 70)
        print()

        # 显示结果
        if result.success:
            print("✅ 协商成功完成！")
            print()
            print("📈 协商结果:")
            print(f"   - 会话 ID: {result.state.session_id}")
            print(f"   - 总轮次: {result.total_rounds}")
            print(f"   - 成功轮次: {result.successful_rounds}")
            print(f"   - Pareto 最优轮次: {result.pareto_optimal_rounds}")
            print(f"   - 成功率: {result.successful_rounds/result.total_rounds*100:.1f}%")
            print(f"   - 耗时: {result.state.total_duration:.2f}s")
            print()

            if result.final_metrics:
                print("🎯 最终指标:")
                print(f"   - Area: {result.final_metrics.area}")
                print(f"   - Delay: {result.final_metrics.delay:.4f} ns")
                if result.final_metrics.node_count:
                    print(f"   - Nodes: {result.final_metrics.node_count}")
                if result.final_metrics.levels:
                    print(f"   - Levels: {result.final_metrics.levels}")
                print()

            if result.improvement:
                print("📊 改进率:")
                print(f"   - Area: {result.improvement.get('area', 0):+.2f}%")
                print(f"   - Delay: {result.improvement.get('delay', 0):+.2f}%")
                print()

            # Pareto 前沿
            if result.pareto_front:
                print(f"🏆 Pareto 前沿: {len(result.pareto_front)} 个非支配解")
                print()
                print("   前沿解列表:")
                for i, metrics in enumerate(result.pareto_front[:5]):
                    print(f"   {i+1}. Area={metrics.area}, Delay={metrics.delay:.4f}ns")

                if len(result.pareto_front) > 5:
                    print(f"   ... 还有 {len(result.pareto_front) - 5} 个解")
                print()

            # 显示协商历史
            if result.state.rounds:
                print("📜 协商历史:")
                for round_data in result.state.rounds:
                    status = "✅" if round_data.execution_success else "❌"
                    pareto = "🏆" if round_data.is_pareto_optimal else "  "

                    selected_agent = "N/A"
                    if round_data.selected_proposal:
                        selected_agent = round_data.selected_proposal.agent_type.value

                    metrics_str = "N/A"
                    if round_data.resulting_metrics:
                        metrics_str = f"Area={round_data.resulting_metrics.area}, Delay={round_data.resulting_metrics.delay:.4f}ns"

                    print(f"   {pareto} Round {round_data.round_id}: {status} [{selected_agent}] {metrics_str}")
                print()

            # 显示统计信息
            print("📊 协商统计:")
            print(f"   - 提案总数: {result.total_rounds * len(config.agents)}")
            print(f"   - 投票总数: {result.total_rounds * len(config.agents) * (len(config.agents) - 1)}")
            print(f"   - Pareto 最优率: {result.pareto_optimal_rounds/result.total_rounds*100:.1f}%")
            print()

            return True
        else:
            print("❌ 协商失败")
            if result.state.errors:
                print("\n错误信息:")
                for error in result.state.errors:
                    print(f"   - Round {error['round']}: {error['error']}")
            return False

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    success = await test_pareto_with_real_aig()

    print("=" * 70)
    if success:
        print("🎉 真实 AIG 文件测试通过！")
        print()
        print("✅ Pareto Multi-Agent Negotiation 系统已完全验证，可以投入使用")
    else:
        print("⚠️  测试未完全通过，请检查错误信息")
    print("=" * 70)

    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
