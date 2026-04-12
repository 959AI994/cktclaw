"""
CktMem relevance picker — ask the LLM which markdown memories matter now.

Scans the memory tree, formats a manifest, and parses a JSON path list from
the model response.
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
    Return absolute paths to the most relevant memory files for ``user_query``.

    Args:
        user_query: Latest user text (truncated inside the prompt).
        llm_analyzer: Object exposing ``chat_with_deepseek(messages)``.
        memory_dir: Optional override; defaults to ``get_auto_mem_path()``.
        max_memories: Hard cap on returned files.

    Returns:
        Existing files under ``memory_dir`` (empty list on failure / no hits).
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    memories = scan_memory_files(memory_dir)

    if not memories:
        return []

    manifest = format_memory_manifest(memories)

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
        messages = [{"role": "user", "content": prompt}]
        response = llm_analyzer.chat_with_deepseek(messages)

        if isinstance(response, dict):
            response = response.get("content", "")

        response = response.strip()

        json_match = response
        if '[' in response and ']' in response:
            start = response.index('[')
            end = response.rindex(']') + 1
            json_match = response[start:end]

        selected_files = json.loads(json_match)

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
    Concatenate memory bodies into a single markdown document.

    Args:
        memory_paths: Absolute paths produced by ``find_relevant_memories``.

    Returns:
        Markdown string suitable for injection into context.
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
    import asyncio
    from models.llm_analyzer import LLMVerilogAnalyzer

    async def test():
        print("CktMem find_relevant_memories smoke test")
        print("=" * 60)

        try:
            llm = LLMVerilogAnalyzer(verbose=False)
            print("LLM analyzer loaded")
        except Exception as e:
            print(f"Failed to load LLM: {e}")
            return

        test_queries = [
            "What are the project goals?",
            "Tell me about the user's background",
            "How should I optimize this circuit?",
        ]

        for query in test_queries:
            print(f"\nquery={query}")
            print("-" * 60)

            relevant = await find_relevant_memories(query, llm)

            if relevant:
                print(f"hits={len(relevant)}")
                for path in relevant:
                    print(f"  - {Path(path).name}")

                content = await load_memory_contents(relevant)
                print(f"\npreview_first_200:\n{content[:200]}...")
            else:
                print("no relevant memories")

        print("\n" + "=" * 60)

    asyncio.run(test())
