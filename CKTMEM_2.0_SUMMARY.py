"""
CktMem 2.0 重构完成总结

完全参考 Claude Code 的 memdir 实现
从数据库记忆系统迁移到文件系统记忆系统
"""

# ═══════════════════════════════════════════════════════════════
# 重构概述
# ═══════════════════════════════════════════════════════════════

## 核心变化

### 之前（CktMem 1.0 - 数据库方式）
- 记忆存储在 SQLite 数据库中
- 只能通过 /reverse 命令触发 Session Memory
- Anchor Memory 概念不够灵活
- AI 无法自主决定何时保存记忆

### 现在（CktMem 2.0 - 文件系统方式）
- 记忆存储在磁盘上的 markdown 文件中
- 每次对话自动加载记忆到 System Prompt
- AI 可以使用 Write/Edit 工具自主保存记忆
- 按语义主题组织，不是按时间或命令

# ═══════════════════════════════════════════════════════════════
# 新架构
# ═══════════════════════════════════════════════════════════════

## 1. 记忆存储位置

默认路径：
~/.cktclaw/projects/<sanitized_project_root>/memory/

例如：
/home/user/.cktclaw/projects/home_user_code_cktclaw/memory/

环境变量覆盖：
export CKTCLAW_MEMORY_PATH_OVERRIDE=/custom/path/memory

## 2. 文件结构

memory/
├── MEMORY.md                    # 索引文件（总是加载）
├── user_background.md           # 用户背景
├── project_goals.md             # 项目目标
├── circuit_adder.md             # 电路分析
├── optimization_strategy.md     # 优化策略
└── design_decisions.md          # 设计决策

## 3. 记忆文件格式

每个记忆文件包含 frontmatter + 内容：

```markdown
---
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
```

## 4. MEMORY.md 索引格式

```markdown
# Memory Index

- [User Background](user_background.md) — EDA engineer focusing on ASAP7
- [Project Goals](project_goals.md) — Low-power RISC-V CPU design
- [Circuit Adder](circuit_adder.md) — 8-bit adder analysis
```

## 5. 记忆类型

- **user**: 用户偏好和背景
- **feedback**: 用户反馈和纠正
- **project**: 项目上下文和需求
- **reference**: 参考信息和工具用法

# ═══════════════════════════════════════════════════════════════
# 实现的模块
# ═══════════════════════════════════════════════════════════════

## cktmem/paths.py
- get_auto_mem_path(): 获取记忆目录路径
- get_project_root(): 获取项目根目录（Git 仓库根）
- is_auto_memory_enabled(): 检查记忆是否启用
- sanitize_path(): 清理路径为安全的目录名

## cktmem/memory_types.py
- MEMORY_TYPES: 记忆类型定义
- build_memory_guidelines(): 构建记忆使用指南
- MEMORY_FRONTMATTER_EXAMPLE: frontmatter 示例

## cktmem/memdir.py
- load_memory_prompt(): 加载记忆提示词（用于 System Prompt）
- truncate_entrypoint_content(): 截断 MEMORY.md 到限制
- ensure_memory_dir_exists(): 确保记忆目录存在

## cktmem/memory_scan.py
- scan_memory_files(): 扫描记忆目录中的所有 .md 文件
- parse_frontmatter(): 解析 markdown frontmatter
- format_memory_manifest(): 格式化记忆清单

## cktmem/find_relevant_memories.py
- find_relevant_memories(): 使用 LLM 找到相关记忆
- load_memory_contents(): 加载记忆文件的完整内容

## cktmem/manager.py（已更新）
- 集成 load_memory_prompt() 到 build_context()
- 每次对话自动加载文件系统记忆

# ═══════════════════════════════════════════════════════════════
# 使用方式
# ═══════════════════════════════════════════════════════════════

## 1. 自动加载记忆（每次对话）

```python
from cktmem import ContextManager, Storage, CompactConfig

# 初始化
storage = Storage(db_path="cktclaw_sessions.db")
context_manager = ContextManager(
    storage=storage,
    system_prompt=SYSTEM_PROMPT,
    config=CompactConfig(),
    project_root="/path/to/project",  # 新增参数
)

# 构建上下文（自动加载文件系统记忆）
messages = await context_manager.build_context(
    session_id=session_id,
    user_message=user_input,
    auto_compact=True,
)

# messages 中会包含：
# 1. System Prompt
# 2. 文件系统记忆提示词（包含 MEMORY.md 索引）
# 3. Project/Session/Turn 层消息
```

## 2. AI 自主保存记忆

AI 可以使用 Write 工具创建记忆文件：

```markdown
User: 记住，这个项目的目标是优化 RISC-V CPU 的面积和功耗

AI: (使用 Write 工具)
    路径: ~/.cktclaw/projects/.../memory/project_goals.md
    内容:
    ---
    name: Project Goals
    description: Optimize RISC-V CPU area and power
    type: project
    ---

    Project goal: Optimize RISC-V CPU for area and power...
```

然后更新 MEMORY.md 索引：

```markdown
AI: (使用 Edit 工具)
    文件: ~/.cktclaw/projects/.../memory/MEMORY.md
    添加: - [Project Goals](project_goals.md) — Optimize RISC-V CPU
```

## 3. 按需检索相关记忆（可选）

```python
from cktmem import find_relevant_memories, load_memory_contents

# 找到相关记忆
relevant_paths = await find_relevant_memories(
    user_query="What are the project goals?",
    llm_analyzer=llm,
)

# 加载内容
memory_content = await load_memory_contents(relevant_paths)

# 添加到上下文
messages.append({
    "role": "system",
    "content": memory_content,
})
```

# ═══════════════════════════════════════════════════════════════
# 与 CktClaw 的集成
# ═══════════════════════════════════════════════════════════════

## 已完成的集成

1. ✅ ContextManager 已更新，自动加载文件系统记忆
2. ✅ 记忆提示词会注入到每次对话的 System Prompt
3. ✅ AI 可以使用 Write/Edit 工具管理记忆文件

## 需要的配置

在初始化 ContextManager 时传入 project_root：

```python
# main.py 或 chat_handler.py
context_manager = ContextManager(
    storage=storage,
    system_prompt=SYSTEM_PROMPT,
    config=CompactConfig(),
    project_root=os.getcwd(),  # 或 get_project_root()
)
```

## System Prompt 中的记忆指南

记忆提示词会自动包含：
- 记忆类型说明（user/feedback/project/reference）
- 如何保存记忆（两步：写文件 + 更新索引）
- 何时访问记忆
- 什么不应该保存
- MEMORY.md 当前索引内容

# ═══════════════════════════════════════════════════════════════
# 测试验证
# ═══════════════════════════════════════════════════════════════

## 运行测试

```bash
# 测试路径管理
python cktmem/paths.py

# 测试记忆加载
python -m cktmem.memdir

# 测试记忆扫描
python -m cktmem.memory_scan

# 完整测试
python test_cktmem_filesystem.py
```

## 验证记忆目录

```bash
ls -la ~/.cktclaw/projects/*/memory/
```

应该看到：
- MEMORY.md
- 各种 topic 文件（*.md）

# ═══════════════════════════════════════════════════════════════
# 迁移指南
# ═══════════════════════════════════════════════════════════════

## 从 CktMem 1.0 迁移

### 旧代码（数据库方式）
```python
# 保存 Anchor Memory
await storage.store_anchor_memory(
    session_id=session_id,
    verilog_code=verilog_code,
    analysis_report=analysis_report,
)
```

### 新代码（文件系统方式）
AI 自动使用 Write 工具保存：
```markdown
---
name: Circuit Adder Analysis
description: 8-bit adder analysis
type: project
---

Module: adder
...
```

### 兼容性

旧的 Storage 类仍然保留，用于：
- Turn Layer 消息存储（对话历史）
- 压缩历史记录
- 会话元数据

新的文件系统记忆用于：
- Session Layer 的持久化记忆
- 项目级上下文
- 用户偏好

# ═══════════════════════════════════════════════════════════════
# 优势
# ═══════════════════════════════════════════════════════════════

✅ 更灵活：不局限于特定命令，AI 自主决定何时保存
✅ 更透明：记忆存储在可读的 markdown 文件中
✅ 更易管理：用户可以直接编辑记忆文件
✅ 更语义化：按主题组织，不是按时间
✅ 更标准：符合 Claude Code 的设计理念
✅ 更可扩展：支持 frontmatter 元数据
✅ 更易调试：可以直接查看记忆文件内容

# ═══════════════════════════════════════════════════════════════
# 下一步
# ═══════════════════════════════════════════════════════════════

1. ✅ 实现文件系统记忆模块
2. ✅ 集成到 ContextManager
3. ⏳ 更新 System Prompt 以包含记忆使用指南（已自动包含）
4. ⏳ 测试 AI 自主保存记忆的能力
5. ⏳ 实现按需检索相关记忆（可选优化）
6. ⏳ 更新 Dashboard 以显示文件系统记忆
7. ⏳ 编写用户文档

# ═══════════════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════════════

CktMem 2.0 已成功实现，完全参考 Claude Code 的 memdir 架构：

- 记忆存储：磁盘上的 markdown 文件
- 记忆组织：MEMORY.md 索引 + 独立 topic 文件
- 记忆加载：每次对话自动加载到 System Prompt
- 记忆管理：AI 使用 Write/Edit 工具自主管理
- 记忆检索：可选的 LLM 驱动的相关记忆检索

系统已准备好与 CktClaw 无缝集成！
"""

print(__doc__)
