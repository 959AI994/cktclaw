# CktMem - 四层上下文记忆管理系统

CktMem 是为 CktClaw 设计的上下文管理模块，实现了四层上下文模型和自动压缩机制。

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│ System Layer (系统层)                                    │
│ - 系统 Prompt                                            │
│ - 工具定义与能力声明                                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Project Layer (项目层)                                   │
│ - 静态工作区状态                                          │
│ - 项目级 Memory 文件                                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Session Layer (会话层)                                   │
│ - Anchor Memory（首份电路分析）                           │
│ - Core Context（后续分析结果）                            │
│ - Compact Summary（压缩摘要）                             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Turn Layer (轮次层)                                      │
│ - 最近 N 轮对话                                           │
│ - 当前用户输入                                            │
└─────────────────────────────────────────────────────────┘
```

## 核心特性

1. **四层上下文隔离**：System / Project / Session / Turn
2. **自动压缩**：Token 阈值触发，支持多种压缩策略
3. **边界标记**：防止语义混淆
4. **溯源管理**：时间戳标记，防止重复

## 快速开始

### 基本使用

```python
from cktmem import ContextManager, Storage, CompactConfig

# 1. 初始化
storage = Storage(db_path="sessions.db")
config = CompactConfig(
    auto_compact_threshold=150_000,
    target_tokens=40_000,
)

context_manager = ContextManager(
    storage=storage,
    system_prompt="Your system prompt here...",
    config=config,
)

# 2. 创建会话
session_id = await storage.create_session(
    session_id="session_001",
    project_name="my_project",
)

# 3. 存储 Anchor Memory
await storage.store_anchor_memory(
    session_id=session_id,
    verilog_code=verilog_code,
    analysis_report=analysis_report,
)

# 4. 构建上下文（自动压缩）
messages = await context_manager.build_context(
    session_id=session_id,
    user_message="用户输入",
    auto_compact=True,
)

# 5. 存储对话
await context_manager.add_assistant_message(
    session_id=session_id,
    content="助手回复",
)
```

### 压缩策略

CktMem 支持三种压缩策略，按优先级自动选择：

1. **Session Memory Compact**（最轻量）
   - 保留后缀消息
   - 不生成摘要
   - 依赖 session layer 语义

2. **Micro Compact**（中等）
   - 清理工具结果
   - 保留工具调用
   - 不调用 LLM

3. **Full Compact**（最重）
   - LLM 生成摘要
   - 保留核心决策
   - 丢弃冗长输出

## 模块结构

```
cktmem/
├── __init__.py          # 包初始化
├── models.py            # 数据模型定义
├── manager.py           # ContextManager（核心）
├── compactor.py         # 压缩器
├── storage.py           # 存储层（SQLite）
├── token_counter.py     # Token 计数器
├── utils.py             # 工具函数
├── example.py           # 使用示例
└── README.md            # 本文档
```

## 配置选项

```python
from cktmem import CompactConfig, SessionMemoryConfig

config = CompactConfig(
    auto_compact_threshold=150_000,  # 自动压缩阈值
    target_tokens=40_000,            # 目标 token 数
    buffer_tokens=13_000,            # 缓冲 token 数
    session_memory=SessionMemoryConfig(
        min_tokens=10_000,           # 最小保留 token
        min_text_messages=5,         # 最小保留消息数
        max_tokens=40_000,           # 最大保留 token
    ),
)
```

## 数据库 Schema

### sessions 表
- `session_id`: 会话 ID（主键）
- `project_name`: 项目名称
- `working_dir`: 工作目录
- `model_choice`: 模型选择
- `anchor_verilog_code`: Anchor Memory（Verilog 代码）
- `anchor_analysis_report`: Anchor Memory（分析报告）
- `total_compactions`: 总压缩次数
- `last_compact_at`: 最后压缩时间

### messages 表
- `id`: 消息 ID（自增主键）
- `session_id`: 会话 ID（外键）
- `role`: 消息角色（system/user/assistant/tool）
- `content`: 消息内容
- `msg_type`: 消息类型（chat/core_context/compact_boundary/compact_summary）
- `layer`: 上下文层级（system/project/session/turn）
- `created_at`: 创建时间
- `metadata`: 元数据（JSON）

### compact_history 表
- `id`: 记录 ID（自增主键）
- `session_id`: 会话 ID（外键）
- `compact_type`: 压缩类型
- `pre_compact_tokens`: 压缩前 token 数
- `post_compact_tokens`: 压缩后 token 数
- `tokens_saved`: 节省的 token 数
- `created_at`: 创建时间

## API 参考

### ContextManager

主要方法：
- `build_context(session_id, user_message, auto_compact)`: 构建完整上下文
- `add_assistant_message(session_id, content, tool_calls)`: 添加助手消息
- `add_tool_result(session_id, tool_call_id, content, name)`: 添加工具结果
- `get_context_stats(session_id)`: 获取上下文统计

### Storage

主要方法：
- `create_session(session_id, project_name, working_dir, model_choice)`: 创建会话
- `get_session(session_id)`: 获取会话信息
- `store_anchor_memory(session_id, verilog_code, analysis_report)`: 存储 Anchor Memory
- `get_anchor_memory(session_id)`: 获取 Anchor Memory
- `add_message(...)`: 添加消息
- `get_messages(session_id, layer, msg_type, limit)`: 获取消息列表
- `add_core_context(session_id, aig_filename, verilog_code, analysis_report)`: 添加核心上下文

### Compactor

主要方法：
- `auto_compact(session_id, messages)`: 自动压缩

### TokenCounter

主要方法：
- `estimate_messages(messages)`: 估算消息列表 token 数
- `estimate_message(message)`: 估算单条消息 token 数

## 运行示例

```bash
cd /home/wjx/pythonproject/cktclaw/cktmem
python example.py
```

## 依赖

- Python 3.8+
- pydantic
- sqlite3（标准库）
- tiktoken（可选，用于更精确的 token 估算）

## 许可证

与 CktClaw 主项目保持一致
