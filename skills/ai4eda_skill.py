"""
AI4EDA Skill - AI4EDA 数据工具技能

将 AI4EDA Toolkit 封装为标准 Harness Skill，支持：
- 工具调用接口标准化
- 输入输出 Pydantic 验证
- 任务生命周期管理
- 错误自愈
"""

import sys
from pathlib import Path

# 确保可以导入 harness
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
import subprocess
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

AI4EDA_BIN = "/home/wjx/pythonproject/AI4EDA-OpenABC-Data-Toolkit/ai4eda-toolkit"


class AI4EDAInput(BaseModel):
    """AI4EDA 工具输入参数"""
    command: str = Field(..., description="AI4EDA 命令")
    timeout: int = Field(default=180, description="超时时间（秒）")


class AI4EDAOutput(BaseModel):
    """AI4EDA 工具输出结果"""
    stdout: str = Field(default="", description="标准输出")
    stderr: str = Field(default="", description="标准错误")
    returncode: int = Field(default=0, description="返回码")
    error: str = Field(default="", description="错误信息")
    success: bool = Field(default=True, description="是否成功")


async def ai4eda_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    AI4EDA 技能执行器

    Args:
        args: 命令参数（AI4EDA 子命令）
        context: 执行上下文（包含 cli_state 等）

    Returns:
        工具结果消息列表
    """
    # 解析输入
    try:
        ai4eda_input = AI4EDAInput(command=args)
    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ AI4EDA 输入参数错误: {e}"
        }]

    # 创建任务
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_BASH,
        f"AI4EDA: {ai4eda_input.command[:50]}..."
    )

    try:
        # 构造完整命令
        full_command = f"{AI4EDA_BIN} {ai4eda_input.command}"

        # 执行 AI4EDA
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=ai4eda_input.timeout,
        )

        # 构造输出
        ai4eda_output = AI4EDAOutput(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.returncode,
            error=result.stderr if result.returncode != 0 else "",
            success=result.returncode == 0,
        )

        # 清理输出
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()

        # 更新任务状态（先检查是否已经是终止状态）
        try:
            if ai4eda_output.success:
                await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
                await task_manager.append_output(
                    task_handle.task_id,
                    f"✅ AI4EDA 执行成功\n{combined or '(无输出)'}"
                )
            else:
                await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
                await task_manager.append_output(
                    task_handle.task_id,
                    f"❌ AI4EDA 执行失败: {ai4eda_output.error}"
                )
        except Exception as task_error:
            # 忽略任务状态更新错误（可能已经是终止状态）
            pass

        # 返回结果
        if ai4eda_output.success:
            return [{
                "type": "text",
                "text": f"✅ AI4EDA 执行成功\n\n```\n{combined or '(无输出)'}\n```"
            }]
        else:
            return [{
                "type": "text",
                "text": f"❌ AI4EDA 执行失败\n\n错误信息:\n```\n{ai4eda_output.error}\n```"
            }]

    except subprocess.TimeoutExpired:
        # 超时处理
        try:
            await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
            await task_manager.append_output(
                task_handle.task_id,
                f"❌ AI4EDA 执行超时（{ai4eda_input.timeout}秒）"
            )
        except:
            pass

        return [{
            "type": "text",
            "text": f"❌ AI4EDA 执行超时（{ai4eda_input.timeout}秒）"
        }]

    except Exception as e:
        # 错误处理
        try:
            await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
            await task_manager.append_output(
                task_handle.task_id,
                f"❌ AI4EDA 执行异常: {str(e)}"
            )
        except:
            pass

        return [{
            "type": "text",
            "text": f"❌ AI4EDA 执行异常: {str(e)}"
        }]


# 定义 AI4EDA Skill
AI4EDA_SKILL = SkillDefinition(
    name="ai4eda",
    skill_type=SkillType.TOOL,
    description="AI4EDA 数据处理工具集",
    display_name="AI4EDA Data Toolkit",
    aliases=["ai4eda-toolkit", "ai4eda-tool"],
    executor=ai4eda_executor,
    loaded_from=LoadedFrom.BUNDLED,
    version="1.0.0",
    metadata={
        "author": "CktClaw Team",
        "category": "data-processing",
        "tags": ["ai4eda", "data", "conversion", "metrics"],
        "binary_path": AI4EDA_BIN,
    }
)


def register():
    """注册 AI4EDA Skill"""
    register_skill(AI4EDA_SKILL)
    return AI4EDA_SKILL


if __name__ == "__main__":
    # 测试 Skill 注册
    skill = register()
    print(f"✓ AI4EDA Skill registered: {skill.name}")
    print(f"  Display Name: {skill.display_name}")
    print(f"  Description: {skill.description}")
    print(f"  Aliases: {skill.aliases}")
