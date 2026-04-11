"""
上下文压缩器

支持多种压缩策略：
1. Session Memory Compact
2. Micro Compact
3. Full Compact
"""

from typing import Optional, List
from datetime import datetime
from .models import (
    Message, MessageRole, MessageType, ContextLayer,
    CompactionResult, CompactConfig, CompactBoundary
)
from .token_counter import TokenCounter
from .storage import Storage


class Compactor:
    """上下文压缩器"""

    def __init__(self, storage: Storage, config: CompactConfig):
        self.storage = storage
        self.config = config
        self.token_counter = TokenCounter()

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
        # 获取最后一个 boundary 之后的消息
        messages_to_compact = self._get_messages_after_last_boundary(messages)

        if not messages_to_compact:
            return None

        # 尝试 Session Memory Compact
        result = await self._try_session_memory_compact(
            session_id,
            messages_to_compact,
        )
        if result:
            return result

        # 尝试 Micro Compact
        result = await self._try_micro_compact(
            session_id,
            messages_to_compact,
        )
        if result:
            return result

        # Full Compact
        return await self._full_compact(
            session_id,
            messages_to_compact,
        )

    def _get_messages_after_last_boundary(
        self,
        messages: List[Message],
    ) -> List[Message]:
        """获取最后一个 boundary 之后的消息"""
        # 找到最后一个 compact_boundary
        last_boundary_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].msg_type == MessageType.COMPACT_BOUNDARY:
                last_boundary_idx = i
                break

        if last_boundary_idx >= 0:
            return messages[last_boundary_idx + 1:]
        else:
            # 只压缩 turn 层消息
            return [m for m in messages if m.layer == ContextLayer.TURN]

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

        pre_tokens = self.token_counter.estimate_messages(messages)
        post_tokens = self.token_counter.estimate_messages([boundary] + messages_to_keep)

        # 记录压缩历史
        await self.storage.record_compaction(
            session_id=session_id,
            compact_type="session_memory",
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=post_tokens,
        )

        return CompactionResult(
            boundary_marker=boundary,
            summary_messages=[],  # Session Memory 不生成摘要
            messages_to_keep=messages_to_keep,
            pre_compact_token_count=pre_tokens,
            post_compact_token_count=post_tokens,
        )

    def _calculate_keep_index(
        self,
        messages: List[Message],
        config,
    ) -> int:
        """计算保留起点索引"""
        # 从后往前累计 token 和文本消息数
        accumulated_tokens = 0
        text_message_count = 0
        keep_index = len(messages)

        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            msg_tokens = self.token_counter.estimate_message(msg)
            accumulated_tokens += msg_tokens

            if msg.role in [MessageRole.USER, MessageRole.ASSISTANT]:
                text_message_count += 1

            # 检查是否满足条件
            if (accumulated_tokens >= config.min_tokens and
                text_message_count >= config.min_text_messages):
                keep_index = i
                break

            # 防止保留过多
            if accumulated_tokens >= config.max_tokens:
                keep_index = i
                break

        return keep_index

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
                tokens_saved += (
                    self.token_counter.estimate_message(msg) -
                    self.token_counter.estimate_message(cleaned)
                )
            else:
                cleaned_messages.append(msg)

        if tokens_saved < 5000:  # 阈值
            return None

        boundary = self._create_boundary(messages, compact_type="micro")

        pre_tokens = self.token_counter.estimate_messages(messages)
        post_tokens = self.token_counter.estimate_messages([boundary] + cleaned_messages)

        # 记录压缩历史
        await self.storage.record_compaction(
            session_id=session_id,
            compact_type="micro",
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=post_tokens,
        )

        return CompactionResult(
            boundary_marker=boundary,
            summary_messages=[],
            messages_to_keep=cleaned_messages,
            pre_compact_token_count=pre_tokens,
            post_compact_token_count=post_tokens,
        )

    def _should_clear_tool_result(self, msg: Message) -> bool:
        """判断是否应该清理工具结果"""
        if msg.role != MessageRole.TOOL:
            return False

        # 检查内容长度
        if len(msg.content) < 1000:
            return False

        return True

    def _clear_tool_result(self, msg: Message) -> Message:
        """清理工具结果"""
        # 保留前 200 字符
        truncated_content = msg.content[:200] + "\n... [truncated for compaction]"

        return Message(
            role=msg.role,
            content=truncated_content,
            msg_type=msg.msg_type,
            layer=msg.layer,
            created_at=msg.created_at,
            metadata={**msg.metadata, "truncated": True},
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
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

        # 创建摘要（简化版，不实际调用 LLM）
        summary = self._generate_simple_summary(messages)

        # 创建 boundary 和 summary
        boundary = self._create_boundary(messages, compact_type="auto")
        summary_message = Message(
            role=MessageRole.USER,
            content=summary,
            msg_type=MessageType.COMPACT_SUMMARY,
            layer=ContextLayer.SESSION,
            metadata={"is_compact_summary": True},
        )

        pre_tokens = self.token_counter.estimate_messages(messages)
        post_tokens = self.token_counter.estimate_messages([boundary, summary_message])

        # 记录压缩历史
        await self.storage.record_compaction(
            session_id=session_id,
            compact_type="auto",
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=post_tokens,
        )

        return CompactionResult(
            boundary_marker=boundary,
            summary_messages=[summary_message],
            messages_to_keep=[],
            pre_compact_token_count=pre_tokens,
            post_compact_token_count=post_tokens,
        )

    def _build_compact_prompt(self, messages: List[Message]) -> str:
        """构造压缩 prompt"""
        prompt = "Please summarize the following conversation, focusing on:\n"
        prompt += "1. Key decisions made\n"
        prompt += "2. Important circuit analysis results\n"
        prompt += "3. User requirements and constraints\n\n"

        for msg in messages:
            if msg.role in [MessageRole.USER, MessageRole.ASSISTANT]:
                prompt += f"{msg.role.value}: {msg.content[:500]}\n\n"

        return prompt

    def _generate_simple_summary(self, messages: List[Message]) -> str:
        """生成简单摘要（不调用 LLM）"""
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]

        summary = "## Conversation Summary\n\n"
        summary += f"Total messages: {len(messages)}\n"
        summary += f"User messages: {len(user_messages)}\n"
        summary += f"Assistant messages: {len(assistant_messages)}\n\n"

        # 提取关键用户问题
        if user_messages:
            summary += "### Key User Questions:\n"
            for i, msg in enumerate(user_messages[:3], 1):
                summary += f"{i}. {msg.content[:100]}...\n"

        return summary

    def _create_boundary(
        self,
        messages: List[Message],
        compact_type: str,
    ) -> Message:
        """创建压缩边界标记"""
        pre_tokens = self.token_counter.estimate_messages(messages)

        boundary_data = CompactBoundary(
            pre_compact_tokens=pre_tokens,
            compact_type=compact_type,
            timestamp=datetime.now(),
        )

        content = "━━━ COMPACT BOUNDARY ━━━\n"
        content += "Previous conversation has been summarized.\n"
        content += f"Pre-compact tokens: {pre_tokens}\n"
        content += f"Compact type: {compact_type}\n"
        content += f"Timestamp: {boundary_data.timestamp.isoformat()}"

        return Message(
            role=MessageRole.SYSTEM,
            content=content,
            msg_type=MessageType.COMPACT_BOUNDARY,
            layer=ContextLayer.SESSION,
            metadata={
                "type": "compact_boundary",
                "pre_compact_tokens": pre_tokens,
                "compact_type": compact_type,
            },
        )
