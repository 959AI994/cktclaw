"""
ABC Skill - ABC 逻辑综合工具技能

将 ABC 工具封装为标准 Harness Skill，支持：
- 工具调用接口标准化
- 输入输出 Pydantic 验证
- 任务生命周期管理
- 错误自愈
"""

import sys
from pathlib import Path

# 确保可以导入 harness
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
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
from cktclaw.eda_tools import ABCRunner
from cktclaw.eda_tools.base_runner import clean_eda_output


class ABCInput(BaseModel):
    """ABC 工具输入参数"""
    command: str = Field(..., description="ABC 命令脚本")
    timeout: int = Field(default=300, description="超时时间（秒）")


class ABCOutput(BaseModel):
    """ABC 工具输出结果"""
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="标准错误")
    returncode: int = Field(default=0, description="返回码")
    error: str = Field(default="", description="错误信息")
    success: bool = Field(default=True, description="是否成功")


async def abc_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ABC 技能执行器

    Args:
        args: 命令参数（ABC 脚本）
        context: 执行上下文（包含 cli_state 等）

    Returns:
        工具结果消息列表
    """
    # 解析输入
    try:
        abc_input = ABCInput(command=args)
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ ABC 输入参数错误: {e}"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_BASH,
        f"ABC: {abc_input.command[:50]}..."
    )

    try:
        # 执行 ABC
        runner = ABCRunner()
        result = runner.run(abc_input.command)

        # 清理输出
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()
        cleaned = clean_eda_output("ABC", combined)

        # 构造输出
        abc_output = ABCOutput(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.returncode,
            error=result.error or "",
            success=not result.error,
        )

        # 更新任务状态
        if abc_output.success:
            await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
            await task_manager.append_output(
                task_handle.task_id,
                f"✅ ABC 执行成功\n{cleaned or '(无输出)'}"
            )
        else:
            await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
            await task_manager.append_output(
                task_handle.task_id,
                f"❌ ABC 执行失败: {abc_output.error}"
            )

        # 返回结果
        if abc_output.success:
            return [{
                "type": "text",
                "text": f"✅ ABC 执行成功\n\n```\n{cleaned or '(无输出)'}\n```"
            }]
        else:
            return [{
                "type": "text",
                "text": f"❌ ABC 执行失败\n\n错误信息:\n```\n{abc_output.error}\n```"
            }]

    except Exception as e:
        # 错误处理
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        await task_manager.append_output(
            task_handle.task_id,
            f"❌ ABC 执行异常: {str(e)}"
        )

        return [{
            "type": "text",
            "text": f"❌ ABC 执行异常: {str(e)}"
        }]


# 定义 ABC Skill
ABC_SKILL = SkillDefinition(
    name="abc",
    skill_type=SkillType.TOOL,
    description="ABC 逻辑综合与验证工具",
    display_name="ABC Logic Synthesis",
    aliases=["abc-tool", "abc-synth"],
    when_to_use=(
        "当需要执行 ABC 逻辑综合、优化、映射或验证时使用此技能。"
        "支持 AIG 结构化、平衡、重写、工艺映射、时序分析等操作。"
    ),
    argument_hint="ABC 命令脚本，例如: read test.aig; strash; balance; print_stats",
    argument_names=["command"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=abc_executor,
)


async def register_abc_skill():
    """注册 ABC 技能"""
    await register_skill(ABC_SKILL)


# 不要在模块导入时自动注册，由 main.py 统一注册
