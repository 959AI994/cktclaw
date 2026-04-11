"""
CktMem 2.0 完整测试

演示基于文件系统的记忆管理系统
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cktmem import (
    get_auto_mem_path,
    load_memory_prompt,
    scan_memory_files,
    format_memory_manifest,
    ensure_memory_dir_exists,
    ENTRYPOINT_NAME,
)


def test_cktmem_filesystem():
    """测试 CktMem 2.0 文件系统记忆"""

    print("=" * 70)
    print("CktMem 2.0 - 基于文件系统的记忆管理测试")
    print("=" * 70)

    # 1. 获取记忆路径
    memory_dir = get_auto_mem_path()
    print(f"\n✓ 记忆目录: {memory_dir}")
    ensure_memory_dir_exists(memory_dir)

    # 2. 创建示例记忆文件
    print("\n" + "=" * 70)
    print("创建示例记忆文件")
    print("=" * 70)

    memory_path = Path(memory_dir)

    # 创建 MEMORY.md 索引
    index_content = """# Memory Index

- [User Background](user_background.md) — EDA engineer focusing on ASAP7
- [Project Goals](project_goals.md) — Low-power RISC-V CPU design
- [Circuit Adder](circuit_adder.md) — 8-bit adder analysis
- [Optimization Strategy](optimization_strategy.md) — Area and power optimization approach
"""

    with open(memory_path / ENTRYPOINT_NAME, 'w', encoding='utf-8') as f:
        f.write(index_content)
    print(f"✓ 创建 {ENTRYPOINT_NAME}")

    # 创建独立的记忆文件
    memories = [
        {
            'filename': 'user_background.md',
            'content': """---
name: User's EDA Background
description: User is an EDA engineer focusing on ASAP7 process
type: user
---

The user is an experienced EDA engineer specializing in ASAP7 process technology.
They prefer Yosys for synthesis and focus on area/power optimization.
They work on RISC-V CPU designs and value clean, efficient implementations.
"""
        },
        {
            'filename': 'project_goals.md',
            'content': """---
name: Project Goals
description: Low-power RISC-V CPU design
type: project
---

**Project**: Design a low-power RISC-V CPU core

**Target Specifications**:
- Clock frequency: 2GHz
- Area: < 0.5mm²
- Power: < 100mW
- Process: ASAP7 (7nm)

**Current Status**: Initial design phase, working on ALU components
"""
        },
        {
            'filename': 'circuit_adder.md',
            'content': """---
name: Circuit Adder Analysis
description: 8-bit adder circuit analysis results
type: project
---

**Module**: adder
**Type**: 8-bit ripple-carry adder

**Analysis Results**:
- Logic gates: 24 (8 full adders)
- Critical path: Carry chain
- Delay: ~1.5ns
- Area: 0.02mm²

**Optimization Notes**: Consider using carry-lookahead for better performance
"""
        },
        {
            'filename': 'optimization_strategy.md',
            'content': """---
name: Optimization Strategy
description: Area and power optimization approach
type: reference
---

**Optimization Priority**:
1. Area optimization first (target < 0.5mm²)
2. Power optimization second (target < 100mW)
3. Timing optimization if needed (target 2GHz)

**Tools**:
- Yosys for synthesis
- ABC for logic optimization
- OpenSTA for timing analysis

**Techniques**:
- Use ASAP7 standard cell library
- Apply aggressive area optimization scripts
- Gate sizing for power reduction
"""
        },
    ]

    for mem in memories:
        file_path = memory_path / mem['filename']
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(mem['content'])
        print(f"✓ 创建 {mem['filename']}")

    # 3. 扫描记忆文件
    print("\n" + "=" * 70)
    print("扫描记忆文件")
    print("=" * 70)

    scanned_memories = scan_memory_files(memory_dir)
    print(f"\n找到 {len(scanned_memories)} 个记忆文件:")
    for mem in scanned_memories:
        fm = mem['frontmatter']
        print(f"  • {mem['name']}")
        print(f"    类型: {fm.get('type', 'unknown')}")
        print(f"    描述: {fm.get('description', '(无)')}")

    # 4. 生成记忆清单
    print("\n" + "=" * 70)
    print("记忆清单")
    print("=" * 70)

    manifest = format_memory_manifest(scanned_memories)
    print(manifest)

    # 5. 加载记忆提示词
    print("\n" + "=" * 70)
    print("加载记忆提示词（用于 System Prompt）")
    print("=" * 70)

    memory_prompt = load_memory_prompt()
    if memory_prompt:
        print(f"\n记忆提示词长度: {len(memory_prompt)} 字符")
        print(f"Token 估算: ~{len(memory_prompt) // 4} tokens")
        print("\n前 800 字符:")
        print(memory_prompt[:800])
        print("...")
    else:
        print("记忆系统已禁用")

    # 6. 总结
    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)

    print(f"""
CktMem 2.0 已成功部署！

记忆存储位置: {memory_dir}

文件结构:
  {ENTRYPOINT_NAME}           - 索引文件（总是加载）
  user_background.md          - 用户背景
  project_goals.md            - 项目目标
  circuit_adder.md            - 电路分析
  optimization_strategy.md    - 优化策略

使用方式:
1. 每次对话自动加载记忆提示词到 System Prompt
2. AI 可以使用 Write/Edit 工具创建/更新记忆文件
3. AI 会自动维护 MEMORY.md 索引
4. 按需检索相关记忆（使用 find_relevant_memories）

与 CktClaw 集成:
- 在 ContextManager.build_context() 中调用 load_memory_prompt()
- 记忆会自动注入到每次对话的上下文中
- AI 自主决定何时保存记忆（通过 Write 工具）

下一步:
1. 更新 ContextManager 以使用新的文件系统记忆
2. 移除旧的数据库记忆代码（或标记为 deprecated）
3. 更新 System Prompt 以包含记忆使用指南
""")


if __name__ == "__main__":
    test_cktmem_filesystem()
