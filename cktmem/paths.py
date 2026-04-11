"""
CktMem Paths - 记忆路径管理

参考 Claude Code 的 paths.ts 实现
负责确定记忆存储位置、路径安全检查
"""

import os
import re
from pathlib import Path
from typing import Optional
import subprocess


def get_project_root() -> Optional[str]:
    """
    获取项目根目录（Git 仓库根）

    Returns:
        Git 仓库根目录的绝对路径，如果不在 Git 仓库中则返回当前工作目录
    """
    try:
        # 尝试获取 Git 根目录
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 不在 Git 仓库中，使用当前工作目录
        return os.getcwd()


def sanitize_path(path: str) -> str:
    """
    清理路径，移除不安全字符

    Args:
        path: 原始路径

    Returns:
        清理后的路径（适合作为目录名）
    """
    # 移除不安全字符，保留字母、数字、下划线、连字符
    sanitized = re.sub(r'[^\w\-]', '_', path)
    # 移除连续的下划线
    sanitized = re.sub(r'_+', '_', sanitized)
    # 移除首尾下划线
    sanitized = sanitized.strip('_')
    return sanitized


def get_memory_base_dir() -> str:
    """
    获取记忆基础目录

    Returns:
        ~/.cktclaw/projects/
    """
    home = Path.home()
    base_dir = home / ".cktclaw" / "projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir)


def get_auto_mem_path(project_root: Optional[str] = None) -> str:
    """
    获取自动记忆路径

    Args:
        project_root: 项目根目录（可选，默认自动检测）

    Returns:
        记忆目录的绝对路径
        例如：~/.cktclaw/projects/my_project_home_user_code/memory/
    """
    # 环境变量覆盖
    override = os.environ.get("CKTCLAW_MEMORY_PATH_OVERRIDE")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    # 获取项目根目录
    if project_root is None:
        project_root = get_project_root()

    # 清理项目路径作为目录名
    sanitized_project = sanitize_path(project_root or "default")

    # 构造记忆路径
    memory_dir = Path(get_memory_base_dir()) / sanitized_project / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    return str(memory_dir)


def is_auto_memory_enabled() -> bool:
    """
    检查自动记忆是否启用

    Returns:
        True 如果启用，False 如果禁用
    """
    # 环境变量禁用
    if os.environ.get("CKTCLAW_DISABLE_AUTO_MEMORY", "").lower() in ["1", "true", "yes"]:
        return False

    # 简化模式禁用
    if os.environ.get("CKTCLAW_SIMPLE", "").lower() in ["1", "true", "yes"]:
        return False

    # 默认启用
    return True


def is_auto_mem_path(path: str, memory_root: Optional[str] = None) -> bool:
    """
    检查路径是否在允许的记忆根目录下

    Args:
        path: 要检查的路径
        memory_root: 记忆根目录（可选，默认使用 get_auto_mem_path()）

    Returns:
        True 如果路径在记忆根目录下
    """
    if memory_root is None:
        memory_root = get_auto_mem_path()

    try:
        path_obj = Path(path).resolve()
        root_obj = Path(memory_root).resolve()
        return path_obj.is_relative_to(root_obj)
    except (ValueError, OSError):
        return False


# 常量
ENTRYPOINT_NAME = "MEMORY.md"
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000


if __name__ == "__main__":
    # 测试路径功能
    print("CktMem Paths 测试")
    print("=" * 60)
    print(f"项目根目录: {get_project_root()}")
    print(f"记忆基础目录: {get_memory_base_dir()}")
    print(f"自动记忆路径: {get_auto_mem_path()}")
    print(f"自动记忆启用: {is_auto_memory_enabled()}")
    print(f"入口文件名: {ENTRYPOINT_NAME}")
    print("=" * 60)
