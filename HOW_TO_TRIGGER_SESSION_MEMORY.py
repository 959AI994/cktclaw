"""
演示如何触发 CktMem 的 Session Layer 记忆

完整流程：
1. 启动 CktClaw
2. 使用 /reverse 处理电路（触发 Anchor Memory）
3. 继续对话（使用 Session 记忆）
4. 再次 /reverse（触发 Core Context）
"""

print("""
╔══════════════════════════════════════════════════════════════╗
║          CktMem Session Layer 记忆触发指南                   ║
╚══════════════════════════════════════════════════════════════╝

## 步骤 1: 启动 CktClaw
$ cktclaw

## 步骤 2: 处理第一个电路（触发 Anchor Memory）
CktClaw > /reverse path/to/adder.aig

这会：
✓ 分析 AIG 文件
✓ 生成 Verilog 代码
✓ 创建分析报告
✓ 存储为 Anchor Memory（Session Layer）

## 步骤 3: 基于 Session 记忆进行对话
CktClaw > 这个电路实现了什么功能？

AI 会使用 Anchor Memory 中的电路信息来回答

CktClaw > 如何优化这个电路？

AI 继续使用 Session 记忆

## 步骤 4: 处理第二个电路（触发 Core Context）
CktClaw > /reverse path/to/multiplier.aig

这会：
✓ 分析新的 AIG 文件
✓ 存储为 Core Context（Session Layer）
✓ 保留之前的 Anchor Memory

## 步骤 5: 查看记忆层级
CktClaw > 现在有哪些电路？

AI 会综合使用：
- Anchor Memory（adder.aig）
- Core Context（multiplier.aig）
- Turn Layer（最近对话）

## 步骤 6: 触发自动压缩（当 Token > 150K）
继续对话，当上下文超过 150K tokens 时：
✓ 自动触发压缩
✓ 生成 Compact Summary（Session Layer）
✓ 保留核心决策
✓ 清理冗余信息

═══════════════════════════════════════════════════════════════

## 验证 Session 记忆

### 方法 1: 查看数据库
$ sqlite3 cktclaw_sessions.db
sqlite> SELECT layer, msg_type, COUNT(*) FROM messages
        WHERE session_id = 'your_session_id'
        GROUP BY layer, msg_type;

期望输出：
session | core_context     | N  (Anchor + Core Contexts)
session | compact_summary  | M  (压缩摘要)
turn    | chat            | X  (对话轮次)

### 方法 2: 使用 Dashboard
$ streamlit run ui/dashboard.py

在 Dashboard 中可以看到：
- 四层上下文的 Token 分布
- Session Layer 的具体内容
- 压缩历史记录

### 方法 3: 运行测试脚本
$ python test_four_layers.py

这会创建一个测试会话，展示所有四层记忆的使用

═══════════════════════════════════════════════════════════════

## 当前限制

目前 Session Layer 主要通过 /reverse 命令触发。
如果你想手动添加 Session 记忆，可以：

```python
# 在 Python 代码中
await storage.add_core_context(
    session_id=session_id,
    aig_filename="my_circuit.aig",
    verilog_code=verilog_code,
    analysis_report=analysis_report,
)
```

或者添加 Project Layer 记忆：

```python
await storage.add_message(
    session_id=session_id,
    role=MessageRole.SYSTEM,
    content="项目级静态信息...",
    layer=ContextLayer.PROJECT,
)
```

═══════════════════════════════════════════════════════════════

## 快速测试

想快速测试 Session 记忆？运行：

$ python test_four_layers.py

这会自动创建一个包含所有四层记忆的测试会话。
""")
