"""
Pareto Negotiation Skill - 多智能体协商技能入口

将 Pareto Multi-Agent Negotiation 封装为标准 Harness Skill。
"""

import sys
from pathlib import Path

# 确保可以导入 harness
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
    get_task_manager,
    TaskType,
    TaskStatus,
)

from workflows.pareto_negotiation import (
    NegotiationCoordinator,
    NegotiationConfig,
    AgentType,
)


class ParetoNegotiationInput(BaseModel):
    """Pareto 协商输入参数"""
    aig_file: str = Field(..., description="AIG 文件路径")
    max_rounds: int = Field(default=50, description="最大协商轮次")
    agents: List[str] = Field(
        default=["area", "delay", "power"],
        description="参与协商的 Agent 列表"
    )
    target_area: int = Field(default=None, description="目标面积")
    target_delay: float = Field(default=None, description="目标延迟")
    convergence_threshold: float = Field(default=0.01, description="收敛阈值")


async def pareto_negotiation_executor(
    args: str,
    context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Pareto 协商技能执行器

    Args:
        args: 命令参数
        context: 执行上下文

    Returns:
        工具结果消息列表
    """
    # 解析参数
    try:
        parts = args.split()
        if not parts:
            return [{
                "type": "text",
                "text": "❌ 请提供 AIG 文件路径\n\n用法: /pareto-negotiate <aig_file> [max_rounds]"
            }]

        aig_file = parts[0]
        max_rounds = int(parts[1]) if len(parts) > 1 else 50

        # 解析 Agent 列表（如果提供）
        agents = ["area", "delay", "power"]
        if len(parts) > 2:
            agents = parts[2].split(",")

        negotiation_input = ParetoNegotiationInput(
            aig_file=aig_file,
            max_rounds=max_rounds,
            agents=agents,
        )
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ 参数错误: {e}\n\n用法: /pareto-negotiate <aig_file> [max_rounds] [agents]"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        f"Pareto Negotiation: {Path(negotiation_input.aig_file).name}"
    )

    try:
        # 配置协商
        agent_types = []
        for agent_str in negotiation_input.agents:
            try:
                agent_types.append(AgentType(agent_str.lower()))
            except ValueError:
                return [{
                    "type": "text",
                    "text": f"❌ 无效的 Agent 类型: {agent_str}\n\n可用类型: area, delay, power"
                }]

        config = NegotiationConfig(
            aig_file_path=negotiation_input.aig_file,
            max_rounds=negotiation_input.max_rounds,
            agents=agent_types,
            target_area=negotiation_input.target_area,
            target_delay=negotiation_input.target_delay,
            convergence_threshold=negotiation_input.convergence_threshold,
        )

        # 运行协商
        coordinator = NegotiationCoordinator()
        result = await coordinator.run(config)

        # 更新任务状态
        if result.success:
            await task_manager.update_task_status(
                task_handle.task_id,
                TaskStatus.COMPLETED
            )
            await task_manager.append_output(task_handle.task_id, result.summary)

            # 构建详细结果
            response_lines = [
                "✅ 多智能体协商完成！",
                "",
                result.summary,
                "",
            ]

            # Pareto 前沿信息
            if result.pareto_front:
                response_lines.append("📊 Pareto 前沿:")
                response_lines.append(f"   共 {len(result.pareto_front)} 个非支配解")
                response_lines.append("")

                # 显示前 5 个解
                for i, metrics in enumerate(result.pareto_front[:5]):
                    response_lines.append(
                        f"   {i+1}. Area={metrics.area}, Delay={metrics.delay:.4f}ns"
                    )

                if len(result.pareto_front) > 5:
                    response_lines.append(f"   ... 还有 {len(result.pareto_front) - 5} 个解")

                response_lines.append("")

            # 协商统计
            response_lines.append("📈 协商统计:")
            response_lines.append(f"   总轮次: {result.total_rounds}")
            response_lines.append(f"   成功轮次: {result.successful_rounds}")
            response_lines.append(f"   Pareto 最优轮次: {result.pareto_optimal_rounds}")
            response_lines.append(f"   成功率: {result.successful_rounds/result.total_rounds*100:.1f}%")

            return [{
                "type": "text",
                "text": "\n".join(response_lines)
            }]
        else:
            await task_manager.update_task_status(
                task_handle.task_id,
                TaskStatus.FAILED
            )
            return [{
                "type": "text",
                "text": f"❌ 协商失败\n\n{result.summary}"
            }]

    except Exception as e:
        await task_manager.update_task_status(
            task_handle.task_id,
            TaskStatus.FAILED
        )
        return [{
            "type": "text",
            "text": f"❌ 协商执行异常: {str(e)}"
        }]


# 定义 Pareto Negotiation Skill
PARETO_NEGOTIATION_SKILL = SkillDefinition(
    name="pareto-negotiate",
    skill_type=SkillType.WORKFLOW,
    description="驱动帕累托最优 PPA 的博弈论多智能体协商协议",
    display_name="Pareto Multi-Agent Negotiation",
    aliases=["pareto", "negotiate", "multi-agent"],
    when_to_use=(
        "当需要通过多智能体协商探索 Pareto 最优 PPA 解空间时使用此技能。"
        "三个专业 Agent（Area, Delay, Power）通过博弈论协商协议，"
        "自动探索并收敛到 Pareto 前沿。"
    ),
    argument_hint="<aig_file> [max_rounds] [agents]",
    argument_names=["aig_file", "max_rounds", "agents"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=pareto_negotiation_executor,
)


async def register_pareto_negotiation_skill():
    """注册 Pareto Negotiation 技能"""
    await register_skill(PARETO_NEGOTIATION_SKILL)
