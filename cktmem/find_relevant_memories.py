"""
CktMem Find Relevant Memories - 相关记忆检索

参考 Claude Code 的 findRelevantMemories.ts 实现
使用 LLM 从记忆清单中选择相关的记忆文件
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from .memory_scan import scan_memory_files, format_memory_manifest
from .paths import get_auto_mem_path


async def find_relevant_memories(
    user_query: str,
    llm_analyzer,
    memory_dir: Optional[str] = None,
    max_memories: int = 5,
) -> List[str]:
    """
    使用 LLM 找到与用户查询相关的记忆文件

    Args:
        user_query: 用户的查询或消息
        llm_analyzer: LLM 分析器实例
        memory_dir: 记忆目录（可选）
        max_memories: 最多返回的记忆文件数

    Returns:
        相关记忆文件的路径列表
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    # 扫描所有记忆文件
    memories = scan_memory_files(memory_dir)

    if not memories:
        return []

    # 格式化清单
    manifest = format_memory_manifest(memories)

    # 构造 LLM prompt
    prompt = f"""You are helping to select relevant memories for the current conversation.

User's current query:
{user_query[:500]}

Available memories:
{manifest}

Select up to {max_memories} memory files that are most relevant to the user's query.
Consider:
- Direct relevance to the query topic
- User preferences that might affect the response
- Project context that provides necessary background
- Recent memories are generally more relevant than old ones

Respond with ONLY a JSON array of relative file paths, like:
["user_background.md", "project_goals.md"]

If no memories are relevant, respond with an empty array: []
"""

    try:
        # 调用 LLM
        messages = [{"role": "user", "content": prompt}]
        response = llm_analyzer.chat_with_deepseek(messages)

        if isinstance(response, dict):
            response = response.get("content", "")

        # 解析 JSON 响应
        response = response.strip()

        # 提取 JSON 数组
        json_match = response
        if '[' in response and ']' in response:
            start = response.index('[')
            end = response.rindex(']') + 1
            json_match = response[start:end]

        selected_files = json.loads(json_match)

        # 验证并返回完整路径
        memory_path = Path(memory_dir)
        relevant_paths = []

        for file_name in selected_files[:max_memories]:
            file_path = memory_path / file_name
            if file_path.exists():
                relevant_paths.append(str(file_path))

        return relevant_paths

    except Exception as e:
        print(f"Warning: Failed to find relevant memories: {e}")
        return []


async def load_memory_contents(memory_paths: List[str]) -> str:
    """
    加载记忆文件的完整内容

    Args:
        memory_paths: 记忆文件路径列表

    Returns:
        格式化的记忆内容
    """
    if not memory_paths:
        return ""

    lines = ["# Relevant Memories", ""]

    for path in memory_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            file_name = Path(path).name
            lines.append(f"## {file_name}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

        except Exception as e:
            print(f"Warning: Failed to load {path}: {e}")
            continue

    return "\n".join(lines)


if __name__ == "__main__":
    # 测试相关记忆检索
    import asyncio
    from models.llm_analyzer import LLMVerilogAnalyzer

    async def test():
        print("CktMem Find Relevant Memories 测试")
        print("=" * 60)

        # 初始化 LLM
        try:
            llm = LLMVerilogAnalyzer(verbose=False)
            print("✓ LLM 分析器已加载")
        except Exception as e:
            print(f"✗ 无法加载 LLM: {e}")
            return

        # 测试查询
        test_queries = [
            "What are the project goals?",
            "Tell me about the user's background",
            "How should I optimize this circuit?",
        ]

        for query in test_queries:
            print(f"\n查询: {query}")
            print("-" * 60)

            relevant = await find_relevant_memories(query, llm)

            if relevant:
                print(f"找到 {len(relevant)} 个相关记忆:")
                for path in relevant:
                    print(f"  - {Path(path).name}")

                # 加载内容
                content = await load_memory_contents(relevant)
                print(f"\n内容预览 (前 200 字符):")
                print(content[:200] + "...")
            else:
                print("未找到相关记忆")

        print("\n" + "=" * 60)

    asyncio.run(test())
