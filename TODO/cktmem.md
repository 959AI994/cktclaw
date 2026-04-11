╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 CktMem 架构设计方案

 一、背景与目标

 当前问题

 CktClaw 现有的记忆系统存在以下问题：
 1. 记忆失效：长对话后早期上下文丢失
 2. 语义冲突：压缩历史与新历史混淆
 3. Token 浪费：冗长的工具执行日志占用大量上下文
 4. 缺乏层级隔离：系统规则、项目状态、会话历史混在一起

 设计目标

 参考 Claude Code 的 Harness Engineering 实践，设计 Python 版本的 cktmem 模块，实现：
 1. 四层上下文隔离：System / Project / Session / Turn
 2. 自动上下文压缩：Token 阈值触发，保留核心决策
 3. 边界隔离标记：防止语义混淆
 4. 溯源与去重：时间戳标记，防止重复

 二、核心架构

 2.1 四层上下文模型

 ┌─────────────────────────────────────────────────────────┐
 │ System Layer (系统层)                                    │
 │ - 系统 Prompt                                            │
 │ - 工具定义与能力声明                                      │
 │ - 全局规则与约束                                          │
 └─────────────────────────────────────────────────────────┘
                           ↓
 ┌─────────────────────────────────────────────────────────┐
 │ Project Layer (项目层)                                   │
 │ - 静态工作区状态（电路文件路径、特征）                      │
 │ - 项目级 Memory 文件                                      │
 │ - 长期知识库                                              │
 └─────────────────────────────────────────────────────────┘
                           ↓
 ┌─────────────────────────────────────────────────────────┐
 │ Session Layer (会话层)                                   │
 │ - 首份 Verilog 代码 + 分析报告（Anchor Memory）           │
 │ - 后续电路分析结果（Core Context）                         │
 │ - 压缩后的历史摘要（Compact Boundary + Summary）          │
 └─────────────────────────────────────────────────────────┘
                           ↓
 ┌─────────────────────────────────────────────────────────┐
 │ Turn Layer (轮次层)                                      │
 │ - 最近 N 轮对话（滑动窗口）                                │
 │ - 当前用户输入                                            │
 │ - 工具调用与结果                                          │
 └─────────────────────────────────────────────────────────┘

 2.2 压缩策略

 触发条件

 - Token 阈值：当前上下文超过 AUTO_COMPACT_THRESHOLD
 - 时间阈值：距离上次对话超过 60 分钟（可选）
 - 手动触发：用户执行 /compact 命令

 压缩流程

 1. 检测是否需要压缩
    ├─ Token 估算
    └─ 阈值判断

 2. 选择压缩策略
    ├─ Session Memory Compact（优先）
    │  └─ 保留后缀消息，前缀交给 session memory
    ├─ Micro Compact
    │  └─ 清理工具结果、媒体块
    └─ Full Compact
       └─ LLM 总结整段历史

 3. 插入 Compact Boundary
    └─ 标记压缩点，防止重复压缩

 4. 重建附件
    └─ 恢复关键文件引用

 2.3 边界隔离机制

 # Compact Boundary Message
 {
     "role": "system",
     "content": "━━━ COMPACT BOUNDARY ━━━\n"
                "Previous conversation has been summarized.\n"
                "Pre-compact tokens: 150000\n"
                "Timestamp: 2024-01-15T10:30:00Z",
     "metadata": {
         "type": "compact_boundary",
         "pre_compact_tokens": 150000,
         "compact_type": "auto",
         "anchor_uuid": "abc123"
     }
 }

 三、数据模型设计

 3.1 核心类型定义

 # models.py

 from enum import Enum
 from typing import Literal, Optional, Union, List, Dict, Any
 from pydantic import BaseModel, Field
 from datetime import datetime

 class MessageRole(str, Enum):
     """消息角色"""
     SYSTEM = "system"
     USER = "user"
     ASSISTANT = "assistant"
     TOOL = "tool"

 class MessageType(str, Enum):
     """消息类型"""
     CHAT = "chat"                    # 普通对话
     CORE_CONTEXT = "core_context"    # 核心上下文（电路分析结果）
     COMPACT_BOUNDARY = "compact_boundary"  # 压缩边界
     COMPACT_SUMMARY = "compact_summary"    # 压缩摘要

 class ContextLayer(str, Enum):
     """上下文层级"""
     SYSTEM = "system"
     PROJECT = "project"
     SESSION = "session"
     TURN = "turn"

 class Message(BaseModel):
     """统一消息结构"""
     role: MessageRole
     content: str
     msg_type: MessageType = MessageType.CHAT
     layer: ContextLayer = ContextLayer.TURN
     created_at: datetime = Field(default_factory=datetime.now)
     metadata: Dict[str, Any] = Field(default_factory=dict)

     # 可选字段
     tool_calls: Optional[List[Dict[str, Any]]] = None
     tool_call_id: Optional[str] = None
     name: Optional[str] = None

 class CompactBoundary(BaseModel):
     """压缩边界标记"""
     pre_compact_tokens: int
     compact_type: Literal["auto", "manual"]
     timestamp: datetime
     anchor_uuid: Optional[str] = None
     preserved_segment_start: Optional[str] = None

 class CompactionResult(BaseModel):
     """压缩结果"""
     boundary_marker: Message
     summary_messages: List[Message]
     messages_to_keep: List[Message] = Field(default_factory=list)
     pre_compact_token_count: int
     post_compact_token_count: int
     compaction_usage: Optional[Dict[str, Any]] = None

 class SessionMemoryConfig(BaseModel):
     """Session Memory 压缩配置"""
     min_tokens: int = 10_000
     min_text_messages: int = 5
     max_tokens: int = 40_000

 class CompactConfig(BaseModel):
     """压缩配置"""
     auto_compact_threshold: int = 150_000
     target_tokens: int = 40_000
     buffer_tokens: int = 13_000
     session_memory: SessionMemoryConfig = Field(default_factory=SessionMemoryConfig)

 3.2 数据库 Schema

 -- sessions 表
 CREATE TABLE IF NOT EXISTS sessions (
     session_id TEXT PRIMARY KEY,
     created_at TEXT NOT NULL DEFAULT (datetime('now')),
     updated_at TEXT NOT NULL DEFAULT (datetime('now')),

     -- 项目信息
     project_name TEXT,
     working_dir TEXT,

     -- 引擎配置
     model_choice TEXT DEFAULT 'logicrt',

     -- Anchor Memory（首份核心上下文）
     anchor_verilog_code TEXT,
     anchor_analysis_report TEXT,

     -- 压缩统计
     total_compactions INTEGER DEFAULT 0,
     last_compact_at TEXT
 );

 -- messages 表
 CREATE TABLE IF NOT EXISTS messages (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     session_id TEXT NOT NULL,

     -- 消息基本信息
     role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
     content TEXT NOT NULL,
     msg_type TEXT NOT NULL DEFAULT 'chat'
         CHECK(msg_type IN ('chat', 'core_context', 'compact_boundary', 'compact_summary')),
     layer TEXT NOT NULL DEFAULT 'turn'
         CHECK(layer IN ('system', 'project', 'session', 'turn')),

     -- 时间戳
     created_at TEXT NOT NULL DEFAULT (datetime('now')),

     -- 元数据（JSON）
     metadata TEXT,

     -- 外键
     FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
 );

 -- 索引
 CREATE INDEX IF NOT EXISTS idx_messages_session
     ON messages(session_id, created_at);
 CREATE INDEX IF NOT EXISTS idx_messages_layer
     ON messages(session_id, layer, created_at);
 CREATE INDEX IF NOT EXISTS idx_messages_type
     ON messages(session_id, msg_type, created_at);

 -- compact_history 表（压缩历史记录）
 CREATE TABLE IF NOT EXISTS compact_history (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     session_id TEXT NOT NULL,
     compact_type TEXT NOT NULL CHECK(compact_type IN ('auto', 'manual', 'session_memory', 'micro')),
     pre_compact_tokens INTEGER NOT NULL,
     post_compact_tokens INTEGER NOT NULL,
     tokens_saved INTEGER NOT NULL,
     created_at TEXT NOT NULL DEFAULT (datetime('now')),

     FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
 );

 四、核心模块设计

 4.1 模块结构

 cktmem/
 ├── __init__.py
 ├── models.py           # 数据模型定义
 ├── manager.py          # 上下文管理器
 ├── compactor.py        # 压缩器
 ├── storage.py          # 存储层（SQLite）
 ├── token_counter.py    # Token 计数器
 └── utils.py            # 工具函数

 4.2 ContextManager（核心）

 # manager.py

 class ContextManager:
     """
     四层上下文管理器

     职责：
     1. 组装四层上下文
     2. 触发自动压缩
     3. 管理边界标记
     """

     def __init__(
         self,
         storage: Storage,
         system_prompt: str,
         config: CompactConfig,
     ):
         self.storage = storage
         self.system_prompt = system_prompt
         self.config = config
         self.compactor = Compactor(storage, config)
         self.token_counter = TokenCounter()

     async def build_context(
         self,
         session_id: str,
         user_message: str,
         auto_compact: bool = True,
     ) -> List[Message]:
         """
         构建完整上下文

         流程：
         1. 加载四层消息
         2. 估算 Token
         3. 触发压缩（如果需要）
         4. 返回最终消息列表
         """

         # 1. 加载各层消息
         messages = []

         # System Layer
         messages.append(Message(
             role=MessageRole.SYSTEM,
             content=self.system_prompt,
             layer=ContextLayer.SYSTEM,
         ))

         # Project Layer（如果有）
         project_messages = await self.storage.get_project_messages(session_id)
         messages.extend(project_messages)

         # Session Layer
         session_messages = await self._load_session_layer(session_id)
         messages.extend(session_messages)

         # Turn Layer（最近 N 轮）
         turn_messages = await self.storage.get_recent_messages(
             session_id,
             max_rounds=5,
             after_last_boundary=True,
         )
         messages.extend(turn_messages)

         # 2. 添加当前用户输入
         current_message = Message(
             role=MessageRole.USER,
             content=user_message,
             layer=ContextLayer.TURN,
         )
         messages.append(current_message)

         # 3. Token 估算
         total_tokens = self.token_counter.estimate_messages(messages)

         # 4. 自动压缩判断
         if auto_compact and total_tokens > self.config.auto_compact_threshold:
             compaction_result = await self.compactor.auto_compact(
                 session_id,
                 messages,
             )
             if compaction_result:
                 # 重建上下文
                 messages = await self._rebuild_after_compact(
                     session_id,
                     compaction_result,
                     current_message,
                 )

         return messages

     async def _load_session_layer(self, session_id: str) -> List[Message]:
         """加载 Session Layer"""
         messages = []

         # Anchor Memory
         anchor = await self.storage.get_anchor_memory(session_id)
         if anchor:
             messages.append(Message(
                 role=MessageRole.ASSISTANT,
                 content=self._format_anchor_memory(anchor),
                 msg_type=MessageType.CORE_CONTEXT,
                 layer=ContextLayer.SESSION,
             ))

         # Core Contexts（后续电路分析）
         core_contexts = await self.storage.get_core_contexts(session_id)
         messages.extend(core_contexts)

         # Compact Summaries（压缩摘要）
         summaries = await self.storage.get_compact_summaries(session_id)
         messages.extend(summaries)

         return messages

 4.3 Compactor（压缩器）

 # compactor.py

 class Compactor:
     """
     上下文压缩器

     支持多种压缩策略：
     1. Session Memory Compact
     2. Micro Compact
     3. Full Compact
     """

     async def auto_compact(
         self,
         session_id: str,
         messages: List[Message],
     ) -> Optional[CompactionResult]:
         """
         自动压缩入口

         策略优先级：
         1. Session Memory Compact（最轻量）
         2. Micro Compact（中等）
         3. Full Compact（最重）
         """

         # 1. 获取最后一个 boundary 之后的消息
         messages_to_compact = self._get_messages_after_last_boundary(messages)

         if not messages_to_compact:
             return None

         # 2. 尝试 Session Memory Compact
         result = await self._try_session_memory_compact(
             session_id,
             messages_to_compact,
         )
         if result:
             return result

         # 3. 尝试 Micro Compact
         result = await self._try_micro_compact(
             session_id,
             messages_to_compact,
         )
         if result:
             return result

         # 4. Full Compact
         return await self._full_compact(
             session_id,
             messages_to_compact,
         )

     async def _try_session_memory_compact(
         self,
         session_id: str,
         messages: List[Message],
     ) -> Optional[CompactionResult]:
         """
         Session Memory 压缩

         策略：
         - 保留后缀消息（满足 min_tokens + min_text_messages）
         - 前缀消息不生成摘要，依赖 session layer 语义
         """
         config = self.config.session_memory

         # 计算保留起点
         keep_index = self._calculate_keep_index(messages, config)

         if keep_index <= 0:
             return None  # 无法压缩

         # 创建 boundary
         boundary = self._create_boundary(
             messages,
             compact_type="session_memory",
         )

         # 保留的消息
         messages_to_keep = messages[keep_index:]

         return CompactionResult(
             boundary_marker=boundary,
             summary_messages=[],  # Session Memory 不生成摘要
             messages_to_keep=messages_to_keep,
             pre_compact_token_count=self.token_counter.estimate_messages(messages),
             post_compact_token_count=self.token_counter.estimate_messages(
                 [boundary] + messages_to_keep
             ),
         )

     async def _try_micro_compact(
         self,
         session_id: str,
         messages: List[Message],
     ) -> Optional[CompactionResult]:
         """
         Micro 压缩

         策略：
         - 清理工具结果中的冗长输出
         - 保留工具调用本身
         - 不生成 LLM 摘要
         """
         cleaned_messages = []
         tokens_saved = 0

         for msg in messages:
             if self._should_clear_tool_result(msg):
                 # 清理工具结果
                 cleaned = self._clear_tool_result(msg)
                 cleaned_messages.append(cleaned)
                 tokens_saved += self.token_counter.estimate_messages([msg]) - \
                                self.token_counter.estimate_messages([cleaned])
             else:
                 cleaned_messages.append(msg)

         if tokens_saved < 5000:  # 阈值
             return None

         boundary = self._create_boundary(messages, compact_type="micro")

         return CompactionResult(
             boundary_marker=boundary,
             summary_messages=[],
             messages_to_keep=cleaned_messages,
             pre_compact_token_count=self.token_counter.estimate_messages(messages),
             post_compact_token_count=self.token_counter.estimate_messages(
                 [boundary] + cleaned_messages
             ),
         )

     async def _full_compact(
         self,
         session_id: str,
         messages: List[Message],
     ) -> CompactionResult:
         """
         完整压缩（LLM 总结）

         策略：
         - 调用 LLM 生成摘要
         - 保留核心决策
         - 丢弃冗长的工具输出
         """
         # 构造压缩 prompt
         compact_prompt = self._build_compact_prompt(messages)

         # 调用 LLM
         summary = await self._call_llm_for_summary(compact_prompt)

         # 创建 boundary 和 summary
         boundary = self._create_boundary(messages, compact_type="auto")
         summary_message = Message(
             role=MessageRole.USER,
             content=summary,
             msg_type=MessageType.COMPACT_SUMMARY,
             layer=ContextLayer.SESSION,
             metadata={"is_compact_summary": True},
         )

         return CompactionResult(
             boundary_marker=boundary,
             summary_messages=[summary_message],
             messages_to_keep=[],
             pre_compact_token_count=self.token_counter.estimate_messages(messages),
             post_compact_token_count=self.token_counter.estimate_messages(
                 [boundary, summary_message]
             ),
         )

 4.4 TokenCounter（Token 计数器）

 # token_counter.py

 class TokenCounter:
     """
     Token 估算器

     策略：
     - 文本：使用 tiktoken 或粗估（1 token ≈ 4 chars）
     - 工具调用：name + input JSON
     - 最后乘以 4/3 保守系数
     """

     def __init__(self):
         try:
             import tiktoken
             self.encoder = tiktoken.encoding_for_model("gpt-4")
             self.use_tiktoken = True
         except:
             self.use_tiktoken = False

     def estimate_messages(self, messages: List[Message]) -> int:
         """估算消息列表的 token 数"""
         total = 0
         for msg in messages:
             total += self.estimate_message(msg)
         return int(total * 4 / 3)  # 保守系数

     def estimate_message(self, message: Message) -> int:
         """估算单条消息的 token 数"""
         tokens = 0

         # 内容
         if message.content:
             tokens += self._estimate_text(message.content)

         # 工具调用
         if message.tool_calls:
             for tool_call in message.tool_calls:
                 tokens += self._estimate_text(
                     tool_call.get("function", {}).get("name", "") +
                     str(tool_call.get("function", {}).get("arguments", ""))
                 )

         return tokens

     def _estimate_text(self, text: str) -> int:
         """估算文本 token 数"""
         if self.use_tiktoken:
             return len(self.encoder.encode(text))
         else:
             # 粗估：1 token ≈ 4 chars
             return len(text) // 4

 五、使用示例

 # 示例：在 CktClaw 主循环中使用 cktmem

 from cktmem import ContextManager, Storage, CompactConfig
 from cktmem.models import Message, MessageRole, MessageType, ContextLayer

 # 1. 初始化
 storage = Storage(db_path="cktclaw_sessions.db")
 config = CompactConfig(
     auto_compact_threshold=150_000,
     target_tokens=40_000,
 )
 context_manager = ContextManager(
     storage=storage,
     system_prompt=SYSTEM_PROMPT,
     config=config,
 )

 # 2. 创建会话
 session_id = await storage.create_session(
     project_name="my_circuit_project",
     model_choice="logicrt",
 )

 # 3. 存储首份核心上下文（Anchor Memory）
 await storage.store_anchor_memory(
     session_id=session_id,
     verilog_code=verilog_code,
     analysis_report=analysis_report,
 )

 # 4. 用户对话
 user_input = "这个电路实现什么功能？"

 # 5. 构建上下文（自动压缩）
 messages = await context_manager.build_context(
     session_id=session_id,
     user_message=user_input,
     auto_compact=True,
 )

 # 6. 调用 LLM
 response = await llm.chat(messages)

 # 7. 存储对话
 await storage.add_message(
     session_id=session_id,
     role=MessageRole.USER,
     content=user_input,
     msg_type=MessageType.CHAT,
     layer=ContextLayer.TURN,
 )
 await storage.add_message(
     session_id=session_id,
     role=MessageRole.ASSISTANT,
     content=response,
     msg_type=MessageType.CHAT,
     layer=ContextLayer.TURN,
 )

 # 8. 后续电路分析（追加 Core Context）
 await storage.add_core_context(
     session_id=session_id,
     aig_filename="circuit2.aig",
     verilog_code=verilog_code2,
     analysis_report=analysis_report2,
 )

 六、关键文件路径

 需要创建的文件

 /home/wjx/pythonproject/cktclaw/cktmem/
 ├── __init__.py
 ├── models.py           # 数据模型
 ├── manager.py          # ContextManager
 ├── compactor.py        # Compactor
 ├── storage.py          # Storage
 ├── token_counter.py    # TokenCounter
 └── utils.py            # 工具函数

 需要修改的文件

 /home/wjx/pythonproject/cktclaw/
 ├── main.py             # 替换 MemoryManager 为 cktmem
 ├── config.py           # 添加 cktmem 配置
 └── handlers/
     ├── chat_handler.py     # 使用 ContextManager
     ├── reverse_handler.py  # 使用 Storage
     └── session_handler.py  # 使用 Storage

 七、验证方案

 端到端测试

 1. 创建会话
 2. 存储首份电路分析
 3. 进行 10 轮对话
 4. 触发自动压缩
 5. 验证压缩后上下文正确性
 6. 继续对话，验证语义连贯性

 单元测试

 - Token 估算准确性
 - 压缩边界正确性
 - 四层消息隔离
 - 数据库 CRUD 操作

 性能测试

 - 100 轮对话的 Token 增长曲线
 - 压缩前后 Token 对比
 - 压缩耗时统计