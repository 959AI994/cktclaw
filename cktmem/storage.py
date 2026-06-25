"""
SQLite storage — sessions, layered messages, anchors, compaction history.

Owns schema bootstrap plus CRUD helpers used by ``ContextManager`` and
``Compactor``.
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
    """Thin async façade over sqlite3 for CktMem legacy mode."""

    def __init__(self, db_path: str = "cktclaw_sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables and indexes when missing."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # sessions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),

                project_name TEXT,
                working_dir TEXT,
                model_choice TEXT DEFAULT 'logicrt',
                session_title TEXT,

                anchor_verilog_code TEXT,
                anchor_analysis_report TEXT,

                total_compactions INTEGER DEFAULT 0,
                last_compact_at TEXT
            )
        """)

        # messages
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

        # indexes
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

        # compact_history
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

        # session_memories
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                summary TEXT,
                content TEXT NOT NULL,
                memory_type TEXT DEFAULT 'general',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),

                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()

    def _get_connection(self):
        """Open a new sqlite connection (callers must close)."""
        return sqlite3.connect(self.db_path)

    async def create_session(
        self,
        session_id: str,
        project_name: Optional[str] = None,
        working_dir: Optional[str] = None,
        model_choice: str = "logicrt",
    ) -> str:
        """Insert a sessions row."""
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
        """Return session metadata dict or None."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    async def delete_session(self, session_id: str) -> bool:
        """
        Remove a session row. Dependent rows (messages, compact_history, session_memories)
        are removed when FOREIGN KEY constraints are enabled (PRAGMA foreign_keys=ON).
        """
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    async def update_session(
        self,
        session_id: str,
        project_name: Optional[str] = None,
        working_dir: Optional[str] = None,
        model_choice: Optional[str] = None,
        session_title: Optional[str] = None,
    ):
        """Patch optional session columns."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build update query dynamically
        updates = []
        params = []

        if project_name is not None:
            updates.append("project_name = ?")
            params.append(project_name)

        if working_dir is not None:
            updates.append("working_dir = ?")
            params.append(working_dir)

        if model_choice is not None:
            updates.append("model_choice = ?")
            params.append(model_choice)

        if session_title is not None:
            updates.append("session_title = ?")
            params.append(session_title)

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(session_id)

            query = f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?"
            cursor.execute(query, params)
            conn.commit()

        conn.close()

    async def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Recent sessions ordered by ``updated_at``."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                session_id,
                session_title,
                project_name,
                model_choice,
                created_at,
                updated_at,
                total_compactions
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    async def store_anchor_memory(
        self,
        session_id: str,
        verilog_code: str,
        analysis_report: str,
    ):
        """Persist verilog + analysis snapshot on the session row."""
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
        """Hydrate ``AnchorMemory`` when anchor verilog exists."""
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
        """Insert a message row; returns sqlite ``lastrowid``."""
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
        """Ordered messages with optional layer/type filters."""
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
        """Recent turn-layer traffic, optionally after last compact boundary."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if after_last_boundary:
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

        if not after_last_boundary:
            messages = messages[-max_rounds * 2:]

        return messages

    async def get_project_messages(self, session_id: str) -> List[Message]:
        """All ``project`` layer rows."""
        return await self.get_messages(session_id, layer=ContextLayer.PROJECT)

    async def get_core_contexts(self, session_id: str) -> List[Message]:
        """Persisted circuit core-context blobs."""
        return await self.get_messages(session_id, msg_type=MessageType.CORE_CONTEXT)

    async def get_compact_summaries(self, session_id: str) -> List[Message]:
        """Post-compaction summary messages."""
        return await self.get_messages(session_id, msg_type=MessageType.COMPACT_SUMMARY)

    async def add_core_context(
        self,
        session_id: str,
        aig_filename: str,
        verilog_code: str,
        analysis_report: str,
    ):
        """Store a formatted analysis block as ``CORE_CONTEXT``."""
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
        """Append compact_history and bump session counters."""
        conn = self._get_connection()
        cursor = conn.cursor()

        tokens_saved = pre_compact_tokens - post_compact_tokens

        cursor.execute("""
            INSERT INTO compact_history (
                session_id, compact_type, pre_compact_tokens,
                post_compact_tokens, tokens_saved
            ) VALUES (?, ?, ?, ?, ?)
        """, (session_id, compact_type, pre_compact_tokens, post_compact_tokens, tokens_saved))

        # bump session compaction stats
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
        """Delete stale turn rows before a compaction boundary id."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM messages
            WHERE session_id = ? AND id < ? AND layer = 'turn'
        """, (session_id, boundary_id))

        conn.commit()
        conn.close()

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        """Map sqlite row -> ``Message`` model."""
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

    # --- Session memory (SQLite) ---

    async def save_session_memory(
        self,
        session_id: str,
        topic: str,
        summary: str,
        content: str,
        memory_type: str = "general",
    ):
        """
        Upsert a keyed memory row for ``topic``.

        Args:
            session_id: Owning chat session.
            topic: Stable slug (e.g. ``circuit_adder``).
            summary: One-line index blurb.
            content: Full markdown body.
            memory_type: general | circuit | requirement | decision, etc.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Keep this robust even if historical DBs do not have
        # UNIQUE(session_id, topic) defined in DDL.
        cursor.execute("""
            SELECT id
            FROM session_memories
            WHERE session_id = ? AND topic = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
        """, (session_id, topic))
        row = cursor.fetchone()

        if row:
            cursor.execute("""
                UPDATE session_memories
                SET summary = ?, content = ?, memory_type = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (summary, content, memory_type, row[0]))
        else:
            cursor.execute("""
                INSERT INTO session_memories (session_id, topic, summary, content, memory_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (session_id, topic, summary, content, memory_type))

        conn.commit()
        conn.close()

    async def get_session_memories(self, session_id: str) -> List[Dict[str, Any]]:
        """Return memory dicts newest-first."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT topic, summary, content, memory_type, created_at, updated_at
            FROM session_memories
            WHERE session_id = ?
            ORDER BY updated_at DESC
        """, (session_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    async def count_session_memories(self) -> int:
        """Return total session memory rows across all sessions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM session_memories")
        count = cursor.fetchone()[0]
        conn.close()
        return int(count)

    async def list_all_session_memories(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return session memory dicts across all sessions, newest-first."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT session_id, topic, summary, content, memory_type, created_at, updated_at
            FROM session_memories
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    async def delete_session_memory(self, session_id: str, topic: str):
        """Delete a topic row."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM session_memories
            WHERE session_id = ? AND topic = ?
        """, (session_id, topic))

        conn.commit()
        conn.close()

    async def format_session_memory(self, session_id: str) -> str:
        """Render sqlite session memories as pseudo-MARKDOWN.md text."""
        memories = await self.get_session_memories(session_id)

        if not memories:
            return ""

        lines = [
            "# Session Memory",
            "",
            "This session has the following memories:",
            "",
        ]

        for mem in memories:
            lines.append(f"- [{mem['topic']}] {mem['summary']}")

        lines.append("")
        lines.append("---")
        lines.append("")

        for mem in memories:
            lines.append(f"## {mem['topic']}")
            lines.append("")
            lines.append(mem['content'])
            lines.append("")

        return "\n".join(lines)

