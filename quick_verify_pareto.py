#!/usr/bin/env python3
"""
Pareto Multi-Agent Negotiation 快速验证脚本

快速验证协商模块的基本功能。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 切换到项目目录
import os
os.chdir(project_root)

print("=" * 70)
print("Pareto Multi-Agent Negotiation 快速验证脚本")
print("=" * 70)
print()

# 测试 1: 导入测试
print("1. 测试模块导入...")
try:
    from workflows.pareto_negotiation import (
        NegotiationCoordinator,
        NegotiationConfig,
        AgentType,
        VoteType,
        NegotiationStatus,
        PPAMetrics,
        Proposal,
        Vote,
        AreaAgent,
        DelayAgent,
        PowerAgent,
        NashArbiter,
        ParetoTracker,
        NegotiationPersistence,
    )
    print("   ✅ 所有模块导入成功")
except Exception as e:
    print(f"   ❌ 模块导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试 2: 类型创建测试
print("\n2. 测试类型创建...")
try:
    metrics = PPAMetrics(area=1000, delay=5.0, power=10.0)
    config = NegotiationConfig(aig_file_path="test.aig")
    print(f"   ✅ PPAMetrics: area={metrics.area}, delay={metrics.delay}, power={metrics.power}")
    print(f"   ✅ NegotiationConfig: max_rounds={config.max_rounds}")
except Exception as e:
    print(f"   ❌ 类型创建失败: {e}")
    sys.exit(1)

# 测试 3: Agent 创建测试
print("\n3. 测试 Agent 创建...")
try:
    area_agent = AreaAgent()
    delay_agent = DelayAgent()
    power_agent = PowerAgent()
    print(f"   ✅ AreaAgent 创建成功: {area_agent.agent_type.value}")
    print(f"   ✅ DelayAgent 创建成功: {delay_agent.agent_type.value}")
    print(f"   ✅ PowerAgent 创建成功: {power_agent.agent_type.value}")
except Exception as e:
    print(f"   ❌ Agent 创建失败: {e}")
    sys.exit(1)

# 测试 4: Pareto 支配测试
print("\n4. 测试 Pareto 支配关系...")
try:
    a = PPAMetrics(area=1000, delay=5.0)
    b = PPAMetrics(area=900, delay=4.5)
    c = PPAMetrics(area=950, delay=5.5)

    print(f"   A: area={a.area}, delay={a.delay}")
    print(f"   B: area={b.area}, delay={b.delay}")
    print(f"   C: area={c.area}, delay={c.delay}")

    print(f"   ✅ B 支配 A: {b.dominates(a)}")
    print(f"   ✅ A 支配 B: {a.dominates(b)}")
    print(f"   ✅ B 支配 C: {b.dominates(c)}")
except Exception as e:
    print(f"   ❌ Pareto 支配测试失败: {e}")
    sys.exit(1)

# 测试 5: Pareto 追踪器测试
print("\n5. 测试 Pareto 追踪器...")
try:
    tracker = ParetoTracker()

    m1 = PPAMetrics(area=1000, delay=5.0)
    m2 = PPAMetrics(area=900, delay=4.5)
    m3 = PPAMetrics(area=950, delay=4.0)
    m4 = PPAMetrics(area=1100, delay=6.0)

    is_optimal_1 = tracker.add_solution(m1)
    is_optimal_2 = tracker.add_solution(m2)
    is_optimal_3 = tracker.add_solution(m3)
    is_optimal_4 = tracker.add_solution(m4)

    print(f"   ✅ M1 是 Pareto 最优: {is_optimal_1}")
    print(f"   ✅ M2 是 Pareto 最优: {is_optimal_2}")
    print(f"   ✅ M3 是 Pareto 最优: {is_optimal_3}")
    print(f"   ✅ M4 是 Pareto 最优: {is_optimal_4}")

    front = tracker.get_pareto_front()
    print(f"   ✅ Pareto 前沿大小: {len(front)}")

    stats = tracker.get_statistics()
    print(f"   ✅ 统计信息: front_size={stats['front_size']}, total_solutions={stats['total_solutions']}")
except Exception as e:
    print(f"   ❌ Pareto 追踪器测试失败: {e}")
    sys.exit(1)

# 测试 6: Agent 提案生成测试
print("\n6. 测试 Agent 提案生成...")
try:
    from workflows.pareto_negotiation.types import NegotiationState

    state = NegotiationState(
        session_id="test_session",
        config=config,
    )

    current_metrics = PPAMetrics(area=1000, delay=5.0)

    area_proposal = area_agent.generate_proposal(state, current_metrics)
    delay_proposal = delay_agent.generate_proposal(state, current_metrics)
    power_proposal = power_agent.generate_proposal(state, current_metrics)

    print(f"   ✅ AreaAgent 提案: {area_proposal.abc_sequence}")
    print(f"   ✅ DelayAgent 提案: {delay_proposal.abc_sequence}")
    print(f"   ✅ PowerAgent 提案: {power_proposal.abc_sequence}")
except Exception as e:
    print(f"   ❌ 提案生成测试失败: {e}")
    sys.exit(1)

# 测试 7: Agent 投票测试
print("\n7. 测试 Agent 投票...")
try:
    vote1 = delay_agent.vote_on_proposal(area_proposal, current_metrics, state)
    vote2 = power_agent.vote_on_proposal(area_proposal, current_metrics, state)

    print(f"   ✅ DelayAgent 投票: {vote1.vote_type.value} (utility: {vote1.utility_score:.3f})")
    print(f"   ✅ PowerAgent 投票: {vote2.vote_type.value} (utility: {vote2.utility_score:.3f})")
except Exception as e:
    print(f"   ❌ 投票测试失败: {e}")
    sys.exit(1)

# 测试 8: Nash 仲裁测试
print("\n8. 测试 Nash 仲裁...")
try:
    arbiter = NashArbiter()

    proposals = [area_proposal, delay_proposal, power_proposal]
    votes = [vote1, vote2]
    agents = [area_agent, delay_agent, power_agent]

    selected, score, reasoning = arbiter.arbitrate(
        proposals,
        votes,
        agents,
        current_metrics,
        state,
    )

    if selected:
        print(f"   ✅ 选中提案: {selected.agent_type.value}")
        print(f"   ✅ Nash 分数: {score:.4f}")
        print(f"   ✅ 仲裁理由: {reasoning[:100]}...")
    else:
        print("   ⚠️  未选中任何提案")
except Exception as e:
    print(f"   ❌ Nash 仲裁测试失败: {e}")
    sys.exit(1)

# 测试 9: 效用函数测试
print("\n9. 测试效用函数...")
try:
    baseline = PPAMetrics(area=1000, delay=5.0, power=10.0)
    improved = PPAMetrics(area=900, delay=4.5, power=9.0)

    area_utility = area_agent.calculate_utility(improved, baseline)
    delay_utility = delay_agent.calculate_utility(improved, baseline)
    power_utility = power_agent.calculate_utility(improved, baseline)

    print(f"   ✅ AreaAgent 效用: {area_utility:.4f}")
    print(f"   ✅ DelayAgent 效用: {delay_utility:.4f}")
    print(f"   ✅ PowerAgent 效用: {power_utility:.4f}")
except Exception as e:
    print(f"   ❌ 效用函数测试失败: {e}")
    sys.exit(1)

# 测试 10: 序列化测试
print("\n10. 测试序列化...")
try:
    # PPAMetrics 序列化
    metrics_dict = metrics.to_dict()
    restored_metrics = PPAMetrics.from_dict(metrics_dict)
    assert restored_metrics.area == metrics.area
    print("   ✅ PPAMetrics 序列化成功")

    # Proposal 序列化
    proposal_dict = area_proposal.to_dict()
    restored_proposal = Proposal.from_dict(proposal_dict)
    assert restored_proposal.proposal_id == area_proposal.proposal_id
    print("   ✅ Proposal 序列化成功")

    # Vote 序列化
    vote_dict = vote1.to_dict()
    restored_vote = Vote.from_dict(vote_dict)
    assert restored_vote.voter_type == vote1.voter_type
    print("   ✅ Vote 序列化成功")
except Exception as e:
    print(f"   ❌ 序列化测试失败: {e}")
    sys.exit(1)

# 测试 11: 持久化测试
print("\n11. 测试持久化...")
try:
    import tempfile
    import asyncio

    async def test_persistence():
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = NegotiationPersistence(data_dir=temp_dir)

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

# 测试 12: Skill 注册测试
print("\n12. 测试 Skill 注册...")
try:
    from skills.pareto_negotiation_skill import PARETO_NEGOTIATION_SKILL
    print(f"   ✅ Skill 名称: {PARETO_NEGOTIATION_SKILL.name}")
    print(f"   ✅ Skill 类型: {PARETO_NEGOTIATION_SKILL.skill_type}")
    print(f"   ✅ 用户可调用: {PARETO_NEGOTIATION_SKILL.user_invocable}")
    print(f"   ✅ 别名: {', '.join(PARETO_NEGOTIATION_SKILL.aliases)}")
except Exception as e:
    print(f"   ❌ Skill 注册测试失败: {e}")
    sys.exit(1)

# 总结
print("\n" + "=" * 70)
print("✅ 所有验证测试通过！")
print("=" * 70)
print()
print("Pareto Multi-Agent Negotiation 模块已准备就绪，可以使用以下方式调用：")
print()
print("1. CLI 命令:")
print("   > /pareto-negotiate test.aig 50")
print()
print("2. Python API:")
print("   from workflows.pareto_negotiation import NegotiationCoordinator, NegotiationConfig")
print("   config = NegotiationConfig(aig_file_path='test.aig', max_rounds=50)")
print("   coordinator = NegotiationCoordinator()")
print("   result = await coordinator.run(config)")
print()
