"""
RLTF Skill - 基于工具反馈的强化学习综合序列优化技能

将 RLTF 工作流封装为标准 Harness Skill，支持：
- 用户友好的调用接口
- 任务生命周期管理
- 进度跟踪和报告
"""

import sys
from pathlib import Path

# 确保可以导入 harness 和 workflows
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from cktclaw.harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
    get_task_manager,
    TaskType,
    TaskStatus,
)


class RLTFInput(BaseModel):
    """RLTF 输入参数"""
    aig_file: str = Field(..., description="AIG 文件路径")
    max_iterations: int = Field(default=50, description="最大迭代次数")
    target_area: int = Field(default=None, description="目标面积")
    target_delay: float = Field(default=None, description="目标延迟")


async def rltf_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    RLTF 技能执行器

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
                "text": "❌ 请提供 AIG 文件路径\n\n用法: /rltf <aig_file> [max_iterations]"
            }]

        aig_file = parts[0]
        max_iterations = int(parts[1]) if len(parts) > 1 else 50

        # 验证文件存在
        if not Path(aig_file).exists():
            return [{
                "type": "text",
                "text": f"❌ AIG 文件不存在: {aig_file}"
            }]

        rltf_input = RLTFInput(
            aig_file=aig_file,
            max_iterations=max_iterations
        )

    except ValueError as e:
        return [{
            "type": "text",
            "text": f"❌ 参数错误: {e}\n\n用法: /rltf <aig_file> [max_iterations]"
        }]
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ 参数解析失败: {e}"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        f"RLTF: {Path(rltf_input.aig_file).name}"
    )

    try:
        # 更新任务状态为运行中
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.RUNNING)
        await task_manager.append_output(
            task_handle.task_id,
            f"🚀 启动 RLTF 优化\n"
            f"   文件: {rltf_input.aig_file}\n"
            f"   最大迭代: {rltf_input.max_iterations}\n"
        )

        # 延迟导入 RLTF 模块（避免启动时加载）
        from cktclaw.workflows.rltf import RLTFCoordinator, RLTFConfig

        # 配置 RLTF
        config = RLTFConfig(
            aig_file_path=rltf_input.aig_file,
            max_iterations=rltf_input.max_iterations,
            target_area=rltf_input.target_area,
            target_delay=rltf_input.target_delay,
        )

        # 运行 RLTF
        coordinator = RLTFCoordinator()
        result = await coordinator.run(config)

        # 更新任务状态
        if result.success:
            await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
            await task_manager.append_output(
                task_handle.task_id,
                f"\n✅ RLTF 优化完成\n{result.summary}"
            )

            # 构建详细结果消息
            result_text = [
                "✅ RLTF 优化完成",
                "",
                "📊 最终结果:",
                f"   会话 ID: {result.state.session_id}",
                f"   迭代次数: {result.state.current_iteration}/{config.max_iterations}",
                f"   总耗时: {result.state.total_duration:.2f}s" if result.state.total_duration else "",
                "",
            ]

            if result.improvement:
                result_text.append("🎯 改进率:")
                result_text.append(f"   Area: {result.improvement['area']:+.2f}%")
                result_text.append(f"   Delay: {result.improvement['delay']:+.2f}%")
                if 'power' in result.improvement:
                    result_text.append(f"   Power: {result.improvement['power']:+.2f}%")
                result_text.append("")

            if result.best_metrics:
                result_text.append("📈 最佳指标:")
                result_text.append(f"   Area: {result.best_metrics.area}")
                result_text.append(f"   Delay: {result.best_metrics.delay:.4f} ns")
                if result.best_metrics.power:
                    result_text.append(f"   Power: {result.best_metrics.power:.4f}")
                result_text.append("")

            if result.best_sequence:
                result_text.append("🏆 最佳 ABC 序列:")
                result_text.append(f"```")
                result_text.append(result.best_sequence)
                result_text.append(f"```")
                result_text.append("")

            result_text.append(f"💾 会话数据已保存到: data/rltf_sessions/{result.state.session_id}/")

            return [{
                "type": "text",
                "text": "\n".join(result_text)
            }]

        else:
            await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
            await task_manager.append_output(
                task_handle.task_id,
                "❌ RLTF 优化失败"
            )

            return [{
                "type": "text",
                "text": f"❌ RLTF 优化失败\n\n错误数量: {len(result.state.errors)}"
            }]

    except Exception as e:
        # 错误处理
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        await task_manager.append_output(
            task_handle.task_id,
            f"❌ RLTF 执行异常: {str(e)}"
        )

        return [{
            "type": "text",
            "text": f"❌ RLTF 执行异常: {str(e)}\n\n请检查日志获取详细信息。"
        }]


# 定义 RLTF Skill
RLTF_SKILL = SkillDefinition(
    name="rltf",
    skill_type=SkillType.WORKFLOW,
    description="基于工具反馈的强化学习综合序列优化",
    display_name="RLTF Optimization",
    aliases=["rltf-opt", "rl-synth"],
    when_to_use=(
        "当需要自动探索和优化 ABC 综合序列时使用此技能。"
        "RLTF 使用强化学习驱动 LLM 生成优化序列，以 PPA 指标作为 Reward。"
        "适用于需要大规模探索优化空间的场景。"
    ),
    argument_hint="<aig_file> [max_iterations]",
    argument_names=["aig_file", "max_iterations"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=rltf_executor,
)


async def register_rltf_skill():
    """注册 RLTF 技能"""
    await register_skill(RLTF_SKILL)


# 不要在模块导入时自动注册，由 main.py 统一注册
