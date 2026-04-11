"""
Reverse Skill - AIG 逆向分析技能

将 /reverse 命令封装为标准 Harness Skill，支持：
- AIG → PT → Verilog → Validate → Analyze 完整流程
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


class ReverseInput(BaseModel):
    """Reverse 工具输入参数"""
    aig_path: str = Field(..., description="AIG 文件路径")


class ReverseOutput(BaseModel):
    """Reverse 工具输出结果"""
    success: bool = Field(default=True, description="是否成功")
    verilog_code: str = Field(default="", description="生成的 Verilog 代码")
    analysis_report: str = Field(default="", description="分析报告")
    error: str = Field(default="", description="错误信息")


async def reverse_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Reverse 技能执行器

    Args:
        args: 命令参数（AIG 文件路径）
        context: 执行上下文（包含 cli_state 等）

    Returns:
        工具结果消息列表
    """
    # 解析输入
    try:
        reverse_input = ReverseInput(aig_path=args.strip())
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ Reverse 输入参数错误: {e}"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_BASH,
        f"Reverse: {reverse_input.aig_path}"
    )

    try:
        # 获取 cli_state
        cli_state = context.get("cli_state")
        if not cli_state:
            raise ValueError("cli_state not found in context")

        # 调用原有的 process_aig 函数
        from cktclaw.handlers.aig_handler import process_aig
        await process_aig(reverse_input.aig_path, cli_state)

        # 更新任务状态
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
        await task_manager.append_output(
            task_handle.task_id,
            f"✅ Reverse 分析完成: {reverse_input.aig_path}"
        )

        # 返回结果
        return [{
            "type": "text",
            "text": f"✅ Reverse 分析完成\n\n已完成 AIG → PT → Verilog → Validate → Analyze 流程"
        }]

    except Exception as e:
        # 错误处理
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        await task_manager.append_output(
            task_handle.task_id,
            f"❌ Reverse 执行异常: {str(e)}"
        )

        return [{
            "type": "text",
            "text": f"❌ Reverse 执行异常: {str(e)}"
        }]


# 定义 Reverse Skill
REVERSE_SKILL = SkillDefinition(
    name="reverse",
    skill_type=SkillType.TOOL,
    description="AIG 逆向分析工具",
    display_name="AIG Reverse Engineering",
    aliases=["reverse-aig", "aig-reverse"],
    when_to_use=(
        "当需要对 AIG 文件进行逆向分析时使用此技能。"
        "支持 AIG → PT → Verilog → Validate → Analyze 完整流程。"
    ),
    argument_hint="AIG 文件路径，例如: /path/to/circuit.aig",
    argument_names=["aig_path"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=reverse_executor,
)


async def register_reverse_skill():
    """注册 Reverse 技能"""
    await register_skill(REVERSE_SKILL)
