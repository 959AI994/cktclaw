"""
CktClaw Session Memory 重新设计方案

参考 Claude Code 的 memdir 实现，改进 Session Memory 的触发和使用机制
"""

# ═══════════════════════════════════════════════════════════════
# 问题分析
# ═══════════════════════════════════════════════════════════════

## 当前问题

1. Session Memory 只能通过 /reverse 触发
   - 太局限，无法记住其他重要信息
   - 用户可能想记住：项目需求、设计决策、优化策略等

2. Anchor Memory 概念不够灵活
   - 为什么第一个电路就是"锚点"？
   - 如果用户先讨论需求，后处理电路呢？

3. AI 无法自主决定何时保存记忆
   - Claude Code 中，AI 自己判断什么值得记住
   - CktClaw 是被动的，只在特定命令时存储

# ═══════════════════════════════════════════════════════════════
# 新设计：参考 Claude Code
# ═══════════════════════════════════════════════════════════════

## 核心理念

Session Memory 应该：
1. **每次对话都自动加载**（作为 System Prompt 的一部分）
2. **AI 自主决定何时保存**（通过工具调用）
3. **按语义主题组织**（不是按时间或命令）

## 新的 Session Memory 结构

```
session_memory/
├── SESSION_MEMORY.md          # 索引文件（类似 MEMORY.md）
├── project_requirements.md    # 项目需求
├── circuit_adder.md          # 电路：加法器
├── circuit_multiplier.md     # 电路：乘法器
├── optimization_strategy.md  # 优化策略
├── design_decisions.md       # 设计决策
└── synthesis_results.md      # 综合结果
```

## 触发机制

### 1. 自动加载（每次对话）

```python
# 在 build_context() 中
async def build_context(self, session_id: str, user_message: str):
    messages = []

    # System Layer
    messages.append(system_prompt)

    # Project Layer
    messages.extend(project_messages)

    # Session Layer - 自动加载 Session Memory
    session_memory = await self._load_session_memory(session_id)
    if session_memory:
        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=session_memory,
            layer=ContextLayer.SESSION,
        ))

    # Turn Layer
    messages.extend(recent_turns)

    return messages
```

### 2. AI 自主保存

在 System Prompt 中添加指导：

```markdown
## Session Memory

You have a persistent session memory system. Use it to remember:
- Circuit analysis results
- Project requirements and constraints
- Design decisions and rationale
- Optimization strategies
- Synthesis results and metrics

When to save to session memory:
- User explicitly asks you to remember something
- You complete a circuit analysis (/reverse)
- User provides important project context
- You make a significant design decision
- You discover important insights

How to save:
Use the save_session_memory tool with:
- topic: A semantic topic name (e.g., "circuit_adder", "project_requirements")
- content: The information to remember
- summary: A one-line summary for the index
```

### 3. 提供工具让 AI 保存记忆

```python
# 新增 Skill: save_session_memory
async def save_session_memory_executor(args: str, context: dict):
    """
    保存 Session Memory

    Args format: <topic>|<summary>|<content>
    """
    parts = args.split('|', 2)
    if len(parts) != 3:
        return [{"type": "text", "text": "❌ 格式错误"}]

    topic, summary, content = parts
    session_id = context['cli_state'].session_id

    # 保存到数据库
    await storage.save_session_memory(
        session_id=session_id,
        topic=topic,
        summary=summary,
        content=content,
    )

    return [{"type": "text", "text": f"✓ 已保存到 Session Memory: {topic}"}]
```

## 数据库设计

```sql
-- 新表：session_memories
CREATE TABLE session_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    topic TEXT NOT NULL,           -- 语义主题
    summary TEXT NOT NULL,          -- 一行摘要
    content TEXT NOT NULL,          -- 完整内容
    memory_type TEXT DEFAULT 'general',  -- general, circuit, requirement, decision
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE(session_id, topic)       -- 同一主题只保留最新版本
);

CREATE INDEX idx_session_memories ON session_memories(session_id, updated_at);
```

## 加载逻辑

```python
async def _load_session_memory(self, session_id: str) -> str:
    """
    加载 Session Memory（类似 MEMORY.md）

    Returns:
        格式化的 Session Memory 内容
    """
    memories = await self.storage.get_session_memories(session_id)

    if not memories:
        return ""

    lines = [
        "# Session Memory",
        "",
        "This session has the following memories:",
        "",
    ]

    # 索引部分（类似 MEMORY.md）
    for mem in memories:
        lines.append(f"- [{mem['topic']}] {mem['summary']}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 详细内容
    for mem in memories:
        lines.append(f"## {mem['topic']}")
        lines.append("")
        lines.append(mem['content'])
        lines.append("")

    return "\n".join(lines)
```

# ═══════════════════════════════════════════════════════════════
# 实现步骤
# ═══════════════════════════════════════════════════════════════

## Step 1: 数据库迁移
- 创建 session_memories 表
- 迁移现有的 Anchor Memory 数据

## Step 2: 实现 save_session_memory Skill
- 创建 skills/session_memory_skill.py
- 注册到 Harness

## Step 3: 更新 System Prompt
- 添加 Session Memory 使用指南
- 说明何时保存、如何保存

## Step 4: 修改 ContextManager
- 在 build_context() 中自动加载 Session Memory
- 移除对 Anchor Memory 的特殊处理

## Step 5: 更新 /reverse 命令
- 改为调用 save_session_memory
- 不再直接写入 Anchor Memory

## Step 6: 测试验证
- 测试 AI 自主保存记忆
- 测试记忆在后续对话中的使用
- 测试 Dashboard 显示

# ═══════════════════════════════════════════════════════════════
# 使用示例
# ═══════════════════════════════════════════════════════════════

## 场景 1：用户明确要求记住

User: 记住，这个项目的目标是优化 RISC-V CPU 的面积和功耗

AI: (调用 save_session_memory)
    topic: project_requirements
    summary: 优化 RISC-V CPU 的面积和功耗
    content: 项目目标：优化 RISC-V CPU 的面积和功耗...

## 场景 2：电路分析后自动保存

User: /reverse adder.aig

AI: (分析完成后自动调用 save_session_memory)
    topic: circuit_adder
    summary: 8位加法器电路分析
    content: 模块名：adder\n输入：a[7:0], b[7:0]\n...

## 场景 3：后续对话自动使用记忆

User: 这个项目有哪些电路？

AI: (自动加载 Session Memory，看到 circuit_adder)
    根据 Session Memory，目前有一个 8 位加法器电路...

# ═══════════════════════════════════════════════════════════════
# 优势
# ═══════════════════════════════════════════════════════════════

✓ 更灵活：不局限于 /reverse 命令
✓ 更智能：AI 自主决定何时保存
✓ 更语义化：按主题组织，不是按时间
✓ 更自然：符合 Claude Code 的设计理念
✓ 更易用：用户可以明确要求"记住这个"
"""

print(__doc__)
