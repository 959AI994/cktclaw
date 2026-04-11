"""
File Tools - 文件操作工具

参考 Claude Code 的文件工具实现。

核心功能：
1. FileReadTool - 文件读取
2. FileWriteTool - 文件写入
3. FileEditTool - 文件编辑
4. GlobTool - 文件搜索
5. GrepTool - 内容搜索
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import glob
import re


@dataclass
class FileReadResult:
    """文件读取结果"""
    content: str
    line_count: int
    file_size: int
    encoding: str = "utf-8"


@dataclass
class FileWriteResult:
    """文件写入结果"""
    success: bool
    bytes_written: int
    message: str


@dataclass
class FileEditResult:
    """文件编辑结果"""
    success: bool
    lines_changed: int
    message: str


@dataclass
class GlobResult:
    """文件搜索结果"""
    files: List[str]
    count: int


@dataclass
class GrepResult:
    """内容搜索结果"""
    matches: List[Dict[str, Any]]
    count: int


class FileReadTool:
    """文件读取工具"""

    @staticmethod
    def read(
        file_path: str,
        offset: int = 0,
        limit: Optional[int] = None,
        encoding: str = "utf-8"
    ) -> FileReadResult:
        """
        读取文件

        Args:
            file_path: 文件路径
            offset: 起始行号
            limit: 读取行数限制
            encoding: 文件编码

        Returns:
            文件读取结果
        """
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        # 读取文件
        with open(path, 'r', encoding=encoding) as f:
            lines = f.readlines()

        # 应用偏移和限制
        if offset > 0:
            lines = lines[offset:]

        if limit is not None:
            lines = lines[:limit]

        content = "".join(lines)
        file_size = path.stat().st_size

        return FileReadResult(
            content=content,
            line_count=len(lines),
            file_size=file_size,
            encoding=encoding
        )


class FileWriteTool:
    """文件写入工具"""

    @staticmethod
    def write(
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True
    ) -> FileWriteResult:
        """
        写入文件

        Args:
            file_path: 文件路径
            content: 文件内容
            encoding: 文件编码
            create_dirs: 是否创建目录

        Returns:
            文件写入结果
        """
        path = Path(file_path).expanduser().resolve()

        # 创建目录
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(path, 'w', encoding=encoding) as f:
            bytes_written = f.write(content)

        return FileWriteResult(
            success=True,
            bytes_written=bytes_written,
            message=f"Successfully wrote {bytes_written} bytes to {file_path}"
        )


class FileEditTool:
    """文件编辑工具"""

    @staticmethod
    def edit(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> FileEditResult:
        """
        编辑文件（字符串替换）

        Args:
            file_path: 文件路径
            old_string: 要替换的字符串
            new_string: 新字符串
            replace_all: 是否替换所有匹配

        Returns:
            文件编辑结果
        """
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 读取文件
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 替换
        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            # 只替换第一个匹配
            new_content = content.replace(old_string, new_string, 1)
            count = 1 if old_string in content else 0

        if count == 0:
            return FileEditResult(
                success=False,
                lines_changed=0,
                message=f"String not found: {old_string[:50]}..."
            )

        # 写回文件
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return FileEditResult(
            success=True,
            lines_changed=count,
            message=f"Successfully replaced {count} occurrence(s)"
        )


class GlobTool:
    """文件搜索工具"""

    @staticmethod
    def glob(
        pattern: str,
        path: Optional[str] = None,
        recursive: bool = True
    ) -> GlobResult:
        """
        搜索文件

        Args:
            pattern: Glob 模式
            path: 搜索路径
            recursive: 是否递归搜索

        Returns:
            文件搜索结果
        """
        if path is None:
            path = os.getcwd()

        search_path = Path(path).expanduser().resolve()

        if not search_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # 执行搜索
        if recursive:
            full_pattern = str(search_path / "**" / pattern)
            files = glob.glob(full_pattern, recursive=True)
        else:
            full_pattern = str(search_path / pattern)
            files = glob.glob(full_pattern, recursive=False)

        # 过滤掉目录
        files = [f for f in files if os.path.isfile(f)]

        # 排序
        files.sort()

        return GlobResult(
            files=files,
            count=len(files)
        )


class GrepTool:
    """内容搜索工具"""

    @staticmethod
    def grep(
        pattern: str,
        path: Optional[str] = None,
        file_pattern: Optional[str] = None,
        case_sensitive: bool = True,
        max_results: int = 100
    ) -> GrepResult:
        """
        搜索文件内容

        Args:
            pattern: 搜索模式（正则表达式）
            path: 搜索路径
            file_pattern: 文件模式
            case_sensitive: 是否区分大小写
            max_results: 最大结果数

        Returns:
            内容搜索结果
        """
        if path is None:
            path = os.getcwd()

        search_path = Path(path).expanduser().resolve()

        if not search_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # 编译正则表达式
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        # 获取要搜索的文件
        if file_pattern:
            glob_result = GlobTool.glob(file_pattern, str(search_path))
            files = glob_result.files
        else:
            # 搜索所有文本文件
            glob_result = GlobTool.glob("*", str(search_path))
            files = glob_result.files

        # 搜索内容
        matches = []

        for file_path in files:
            if len(matches) >= max_results:
                break

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if len(matches) >= max_results:
                            break

                        if regex.search(line):
                            matches.append({
                                "file": file_path,
                                "line": line_num,
                                "content": line.rstrip(),
                            })
            except Exception:
                # 跳过无法读取的文件
                continue

        return GrepResult(
            matches=matches,
            count=len(matches)
        )


# 工具注册
FILE_TOOLS = {
    "Read": FileReadTool,
    "Write": FileWriteTool,
    "Edit": FileEditTool,
    "Glob": GlobTool,
    "Grep": GrepTool,
}
