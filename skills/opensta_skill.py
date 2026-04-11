"""
OpenSTA Skill - OpenSTA 静态时序分析工具技能

将 OpenSTA 工具封装为标准 Harness Skill，支持：
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
from cktclaw.eda_tools import OpenSTARunner
from cktclaw.eda_tools.base_runner import clean_eda_output


class OpenSTAInput(BaseModel):
    """OpenSTA 工具输入参数"""
    command: str = Field(..., description="OpenSTA 命令脚本")
    timeout: int = Field(default=300, description="超时时间（秒）")


class OpenSTAOutput(BaseModel):
    """OpenSTA 工具输出结果"""
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="标准错误")
    returncode: int = Field(default=0, description="返回码")
    error: str = Field(default="", description="错误信息")
    success: bool = Field(default=True, description="是否成功")


async def opensta_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    OpenSTA 技能执行器

    Args:
        args: 命令参数（OpenSTA 脚本）
        context: 执行上下文（包含 cli_state 等）

    Returns:
        工具结果消息列表
    """
    # 解析输入
    try:
        opensta_input = OpenSTAInput(command=args)
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ OpenSTA 输入参数错误: {e}"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_BASH,
        f"OpenSTA: {opensta_input.command[:50]}..."
    )

    try:
        # 执行 OpenSTA
        runner = OpenSTARunner()
        result = runner.run(opensta_input.command)

        # 清理输出
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()
        cleaned = clean_eda_output("OpenSTA", combined)

        # 构造输出
        opensta_output = OpenSTAOutput(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.returncode,
            error=result.error or "",
            success=not result.error,
        )

        # 更新任务状态
        try:
            if opensta_output.success:
                await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
                await task_manager.append_output(
                    task_handle.task_id,
                    f"✅ OpenSTA 执行成功\n{cleaned or '(无输出)'}"
                )
            else:
                await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
                await task_manager.append_output(
                    task_handle.task_id,
                    f"❌ OpenSTA 执行失败: {opensta_output.error}"
                )
        except Exception as task_error:
            # 忽略任务状态更新错误（可能已经是终止状态）
            pass

        # 返回结果
        if opensta_output.success:
            return [{
                "type": "text",
                "text": f"✅ OpenSTA 执行成功\n\n```\n{cleaned or '(无输出)'}\n```"
            }]
        else:
            return [{
                "type": "text",
                "text": f"❌ OpenSTA 执行失败\n\n错误信息:\n```\n{opensta_output.error}\n```"
            }]

    except Exception as e:
        # 错误处理
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        await task_manager.append_output(
            task_handle.task_id,
            f"❌ OpenSTA 执行异常: {str(e)}"
        )

        return [{
            "type": "text",
            "text": f"❌ OpenSTA 执行异常: {str(e)}"
        }]


# 定义 OpenSTA Skill
OPENSTA_SKILL = SkillDefinition(
    name="opensta",
    skill_type=SkillType.TOOL,
    description="OpenSTA 静态时序分析工具",
    display_name="OpenSTA Static Timing Analysis",
    aliases=["opensta-tool", "sta"],
    when_to_use=(
        "当需要执行静态时序分析时使用此技能。"
        "支持时序路径分析、建立时间检查、保持时间检查等操作。"
    ),
    argument_hint="OpenSTA 命令脚本，例如: read_liberty lib.lib; read_verilog design.v; report_checks",
    argument_names=["command"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=opensta_executor,
)


async def register_opensta_skill():
    """注册 OpenSTA 技能"""
    await register_skill(OPENSTA_SKILL)
