"""
存储层（SQLite）

负责：
1. 会话管理
2. 消息存储与查询
3. Anchor Memory 管理
4. 压缩历史记录
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager
from .models import (
    Message, MessageRole, MessageType, ContextLayer,
    AnchorMemory, CompactBoundary
)


class Storage:
    """存储层"""

    def __init__(self, db_path: str = "cktclaw_sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # sessions 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),

                project_name TEXT,
                working_dir TEXT,
                model_choice TEXT DEFAULT 'logicrt',

                anchor_verilog_code TEXT,
                anchor_analysis_report TEXT,

                total_compactions INTEGER DEFAULT 0,
                last_compact_at TEXT
            )
        """)

        # messages 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,

                role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                msg_type TEXT NOT NULL DEFAULT 'chat'
                    CHECK(msg_type IN ('chat', 'core_context', 'compact_boundary', 'compact_summary')),
                layer TEXT NOT NULL DEFAULT 'turn'
                    CHECK(layer IN ('system', 'project', 'session', 'turn')),

                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                metadata TEXT,

                tool_calls TEXT,
                tool_call_id TEXT,
                name TEXT,

                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)

        # 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_layer
                ON messages(session_id, layer, created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_type
                ON messages(session_id, msg_type, created_at)
        """)

        # compact_history 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compact_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                compact_type TEXT NOT NULL CHECK(compact_type IN ('auto', 'manual', 'session_memory', 'micro')),
                pre_compact_tokens INTEGER NOT NULL,
                post_compact_tokens INTEGER NOT NULL,
                tokens_saved INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),

                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()

    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    async def create_session(
        self,
        session_id: str,
        project_name: Optional[str] = None,
        working_dir: Optional[str] = None,
        model_choice: str = "logicrt",
    ) -> str:
        """创建会话"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO sessions (session_id, project_name, working_dir, model_choice)
            VALUES (?, ?, ?, ?)
        """, (session_id, project_name, working_dir, model_choice))

        conn.commit()
        conn.close()
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    async def store_anchor_memory(
        self,
        session_id: str,
        verilog_code: str,
        analysis_report: str,
    ):
        """存储 Anchor Memory"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions
            SET anchor_verilog_code = ?,
                anchor_analysis_report = ?,
                updated_at = datetime('now')
            WHERE session_id = ?
        """, (verilog_code, analysis_report, session_id))

        conn.commit()
        conn.close()

    async def get_anchor_memory(self, session_id: str) -> Optional[AnchorMemory]:
        """获取 Anchor Memory"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT anchor_verilog_code, anchor_analysis_report, created_at
            FROM sessions
            WHERE session_id = ?
        """, (session_id,))

        row = cursor.fetchone()
        conn.close()

        if row and row["anchor_verilog_code"]:
            return AnchorMemory(
                verilog_code=row["anchor_verilog_code"],
                analysis_report=row["anchor_analysis_report"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        return None

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        msg_type: MessageType = MessageType.CHAT,
        layer: ContextLayer = ContextLayer.TURN,
        metadata: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> int:
        """添加消息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO messages (
                session_id, role, content, msg_type, layer,
                metadata, tool_calls, tool_call_id, name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            role.value if hasattr(role, 'value') else role,
            content,
            msg_type.value if hasattr(msg_type, 'value') else msg_type,
            layer.value if hasattr(layer, 'value') else layer,
            json.dumps(metadata) if metadata else None,
            json.dumps(tool_calls) if tool_calls else None,
            tool_call_id,
            name,
        ))

        message_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return message_id

    async def get_messages(
        self,
        session_id: str,
        layer: Optional[ContextLayer] = None,
        msg_type: Optional[MessageType] = None,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """获取消息列表"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM messages WHERE session_id = ?"
        params = [session_id]

        if layer:
            query += " AND layer = ?"
            params.append(layer.value)

        if msg_type:
            query += " AND msg_type = ?"
            params.append(msg_type.value)

        query += " ORDER BY created_at ASC"

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_message(row) for row in rows]

    async def get_recent_messages(
        self,
        session_id: str,
        max_rounds: int = 5,
        after_last_boundary: bool = True,
    ) -> List[Message]:
        """获取最近 N 轮消息"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if after_last_boundary:
            # 找到最后一个 boundary
            cursor.execute("""
                SELECT id FROM messages
                WHERE session_id = ? AND msg_type = 'compact_boundary'
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id,))
            boundary_row = cursor.fetchone()

            if boundary_row:
                boundary_id = boundary_row["id"]
                cursor.execute("""
                    SELECT * FROM messages
                    WHERE session_id = ? AND id > ? AND layer = 'turn'
                    ORDER BY created_at ASC
                """, (session_id, boundary_id))
            else:
                cursor.execute("""
                    SELECT * FROM messages
                    WHERE session_id = ? AND layer = 'turn'
                    ORDER BY created_at ASC
                """, (session_id,))
        else:
            cursor.execute("""
                SELECT * FROM messages
                WHERE session_id = ? AND layer = 'turn'
                ORDER BY created_at DESC
                LIMIT ?
            """, (session_id, max_rounds * 2))

        rows = cursor.fetchall()
        conn.close()

        messages = [self._row_to_message(row) for row in rows]

        # 限制轮数
        if not after_last_boundary:
            messages = messages[-max_rounds * 2:]

        return messages

    async def get_project_messages(self, session_id: str) -> List[Message]:
        """获取 Project Layer 消息"""
        return await self.get_messages(session_id, layer=ContextLayer.PROJECT)

    async def get_core_contexts(self, session_id: str) -> List[Message]:
        """获取 Core Context 消息"""
        return await self.get_messages(session_id, msg_type=MessageType.CORE_CONTEXT)

    async def get_compact_summaries(self, session_id: str) -> List[Message]:
        """获取压缩摘要"""
        return await self.get_messages(session_id, msg_type=MessageType.COMPACT_SUMMARY)

    async def add_core_context(
        self,
        session_id: str,
        aig_filename: str,
        verilog_code: str,
        analysis_report: str,
    ):
        """添加 Core Context"""
        content = f"## Circuit Analysis: {aig_filename}\n\n"
        content += f"### Verilog Code\n```verilog\n{verilog_code}\n```\n\n"
        content += f"### Analysis Report\n{analysis_report}"

        await self.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            msg_type=MessageType.CORE_CONTEXT,
            layer=ContextLayer.SESSION,
            metadata={"aig_filename": aig_filename},
        )

    async def record_compaction(
        self,
        session_id: str,
        compact_type: str,
        pre_compact_tokens: int,
        post_compact_tokens: int,
    ):
        """记录压缩历史"""
        conn = self._get_connection()
        cursor = conn.cursor()

        tokens_saved = pre_compact_tokens - post_compact_tokens

        cursor.execute("""
            INSERT INTO compact_history (
                session_id, compact_type, pre_compact_tokens,
                post_compact_tokens, tokens_saved
            ) VALUES (?, ?, ?, ?, ?)
        """, (session_id, compact_type, pre_compact_tokens, post_compact_tokens, tokens_saved))

        # 更新 session
        cursor.execute("""
            UPDATE sessions
            SET total_compactions = total_compactions + 1,
                last_compact_at = datetime('now'),
                updated_at = datetime('now')
            WHERE session_id = ?
        """, (session_id,))

        conn.commit()
        conn.close()

    async def delete_messages_before_boundary(
        self,
        session_id: str,
        boundary_id: int,
    ):
        """删除 boundary 之前的 turn 层消息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM messages
            WHERE session_id = ? AND id < ? AND layer = 'turn'
        """, (session_id, boundary_id))

        conn.commit()
        conn.close()

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        """将数据库行转换为 Message 对象"""
        return Message(
            role=MessageRole(row["role"]),
            content=row["content"],
            msg_type=MessageType(row["msg_type"]),
            layer=ContextLayer(row["layer"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
            tool_call_id=row["tool_call_id"],
            name=row["name"],
        )
