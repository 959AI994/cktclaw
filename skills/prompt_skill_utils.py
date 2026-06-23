"""Shared helpers for markdown-first (PROMPT) skills."""

from pathlib import Path
from typing import Any, Dict, List

from cktclaw.harness import get_task_manager, TaskType, TaskStatus


def make_prompt_executor(skill_path: Path, display_name: str):
    """
    Factory: async executor that injects SKILL.md (+ optional user task) for the LLM.
    """
    skill_root = skill_path.parent

    async def executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        task_manager = get_task_manager()
        task = await task_manager.create_task(TaskType.LOCAL_BASH, f"{display_name} skill")

        try:
            skill_markdown = (
                skill_path.read_text(encoding="utf-8")
                if skill_path.is_file()
                else f"SKILL.md not found: {skill_path}"
            )
            root_line = f"Base directory for this skill: {skill_root}\n\n"

            if not args.strip():
                body = f"# {display_name}\n\n{root_line}{skill_markdown}"
            else:
                body = (
                    f"# {display_name}\n\n"
                    f"{root_line}{skill_markdown}\n\n"
                    f"---\n\n"
                    f"## 用户任务\n\n{args.strip()}"
                )

            await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
            return [{"type": "text", "text": body}]

        except Exception as e:
            from ..runtime.run_context import log_exception
            log_exception(
                __name__,
                "PROMPT skill '%s' failed (task %s): %s", display_name, task.task_id, e,
            )
            await task_manager.update_task_status(task.task_id, TaskStatus.FAILED)
            return [{"type": "text", "text": f"Error in {display_name}: {e}"}]

    return executor
