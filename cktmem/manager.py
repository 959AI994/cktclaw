"""
四层上下文管理器

职责：
1. 组装四层上下文
2. 触发自动压缩
3. 管理边界标记
"""

from typing import List, Optional
from .models import (
    Message, MessageRole, MessageType, ContextLayer,
    CompactConfig, CompactionResult
)
from .storage import Storage
from .compactor import Compactor
from .token_counter import TokenCounter


class ContextManager:
    """四层上下文管理器"""

    def __init__(
        self,
        storage: Storage,
        system_prompt: str,
        config: Optional[CompactConfig] = None,
    ):
        self.storage = storage
        self.system_prompt = system_prompt
        self.config = config or CompactConfig()
        self.compactor = Compactor(storage, self.config)
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

    def _format_anchor_memory(self, anchor) -> str:
        """格式化 Anchor Memory"""
        content = "## Initial Circuit Analysis (Anchor Memory)\n\n"
        content += "### Verilog Code\n```verilog\n"
        content += anchor.verilog_code
        content += "\n```\n\n"
        content += "### Analysis Report\n"
        content += anchor.analysis_report
        return content

    async def _rebuild_after_compact(
        self,
        session_id: str,
        compaction_result: CompactionResult,
        current_message: Message,
    ) -> List[Message]:
        """压缩后重建上下文"""
        messages = []

        # System Layer
        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=self.system_prompt,
            layer=ContextLayer.SYSTEM,
        ))

        # Project Layer
        project_messages = await self.storage.get_project_messages(session_id)
        messages.extend(project_messages)

        # Session Layer
        session_messages = await self._load_session_layer(session_id)
        messages.extend(session_messages)

        # 添加 boundary 和 summary
        await self.storage.add_message(
            session_id=session_id,
            role=compaction_result.boundary_marker.role,
            content=compaction_result.boundary_marker.content,
            msg_type=compaction_result.boundary_marker.msg_type,
            layer=compaction_result.boundary_marker.layer,
            metadata=compaction_result.boundary_marker.metadata,
        )
        messages.append(compaction_result.boundary_marker)

        for summary_msg in compaction_result.summary_messages:
            await self.storage.add_message(
                session_id=session_id,
                role=summary_msg.role,
                content=summary_msg.content,
                msg_type=summary_msg.msg_type,
                layer=summary_msg.layer,
                metadata=summary_msg.metadata,
            )
            messages.append(summary_msg)

        # 保留的消息
        messages.extend(compaction_result.messages_to_keep)

        # 当前用户输入
        messages.append(current_message)

        return messages

    async def add_assistant_message(
        self,
        session_id: str,
        content: str,
        tool_calls: Optional[List] = None,
    ):
        """添加助手消息"""
        await self.storage.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
            tool_calls=tool_calls,
        )

    async def add_tool_result(
        self,
        session_id: str,
        tool_call_id: str,
        content: str,
        name: str,
    ):
        """添加工具结果"""
        await self.storage.add_message(
            session_id=session_id,
            role=MessageRole.TOOL,
            content=content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
            tool_call_id=tool_call_id,
            name=name,
        )

    async def get_context_stats(self, session_id: str) -> dict:
        """获取上下文统计信息"""
        all_messages = await self.storage.get_messages(session_id)
        total_tokens = self.token_counter.estimate_messages(all_messages)

        session_info = await self.storage.get_session(session_id)

        return {
            "total_messages": len(all_messages),
            "total_tokens": total_tokens,
            "total_compactions": session_info.get("total_compactions", 0) if session_info else 0,
            "last_compact_at": session_info.get("last_compact_at") if session_info else None,
        }
