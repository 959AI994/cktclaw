"""
Yosys Skill - Yosys 综合工具技能

将 Yosys 工具封装为标准 Harness Skill，支持：
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
from cktclaw.eda_tools import YosysRunner
from cktclaw.eda_tools.base_runner import clean_eda_output


class YosysInput(BaseModel):
    """Yosys 工具输入参数"""
    command: str = Field(..., description="Yosys 命令脚本")
    timeout: int = Field(default=180, description="超时时间（秒）")


class YosysOutput(BaseModel):
    """Yosys 工具输出结果"""
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="标准错误")
    returncode: int = Field(default=0, description="返回码")
    error: str = Field(default="", description="错误信息")
    success: bool = Field(default=True, description="是否成功")


async def yosys_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Yosys 技能执行器

    Args:
        args: 命令参数（Yosys 脚本）
        context: 执行上下文（包含 cli_state 等）

    Returns:
        工具结果消息列表
    """
    # 解析输入
    try:
        yosys_input = YosysInput(command=args)
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ Yosys 输入参数错误: {e}"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_BASH,
        f"Yosys: {yosys_input.command[:50]}..."
    )

    try:
        # 执行 Yosys
        runner = YosysRunner()
        result = runner.run(yosys_input.command)

        # 清理输出
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()
        cleaned = clean_eda_output("Yosys", combined)

        # 构造输出
        yosys_output = YosysOutput(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.returncode,
            error=result.error or "",
            success=not result.error,
        )

        # 更新任务状态（先检查是否已经是终止状态）
        try:
            if yosys_output.success:
                await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
                await task_manager.append_output(
                    task_handle.task_id,
                    f"✅ Yosys 执行成功\n{cleaned or '(无输出)'}"
                )
            else:
                await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
                await task_manager.append_output(
                    task_handle.task_id,
                    f"❌ Yosys 执行失败: {yosys_output.error}"
                )
        except Exception as task_error:
            # 忽略任务状态更新错误（可能已经是终止状态）
            pass

        # 返回结果
        if yosys_output.success:
            return [{
                "type": "text",
                "text": f"✅ Yosys 执行成功\n\n```\n{cleaned or '(无输出)'}\\n```"
            }]
        else:
            return [{
                "type": "text",
                "text": f"❌ Yosys 执行失败\n\n错误信息:\n```\n{yosys_output.error}\n```"
            }]

    except Exception as e:
        # 错误处理
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        await task_manager.append_output(
            task_handle.task_id,
            f"❌ Yosys 执行异常: {str(e)}"
        )

        return [{
            "type": "text",
            "text": f"❌ Yosys 执行异常: {str(e)}"
        }]


# 定义 Yosys Skill
YOSYS_SKILL = SkillDefinition(
    name="yosys",
    skill_type=SkillType.TOOL,
    description="Yosys 开源综合工具",
    display_name="Yosys Open Synthesis",
    aliases=["yosys-tool", "yosys-synth"],
    when_to_use=(
        "当需要执行 Yosys 综合、优化、映射或分析时使用此技能。"
        "支持 Verilog 读取、综合、工艺映射、统计分析等操作。"
    ),
    argument_hint="Yosys 命令脚本，例如: read_verilog test.v; synth -top m0; stat",
    argument_names=["command"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=yosys_executor,
)


async def register_yosys_skill():
    """注册 Yosys 技能"""
    await register_skill(YOSYS_SKILL)
