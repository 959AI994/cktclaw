"""
Negotiation Persistence - 协商历史持久化

管理协商状态的保存和加载。
"""

import json
import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from .types import NegotiationState


class NegotiationPersistence:
    """
    协商持久化管理器

    职责：
    1. 保存协商状态到磁盘
    2. 加载历史协商状态
    3. 管理检查点
    4. 清理过期数据
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        初始化持久化管理器

        Args:
            data_dir: 数据目录，默认为 data/negotiation_sessions/
        """
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path("data/negotiation_sessions")

        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def save_checkpoint(self, state: NegotiationState):
        """
        保存检查点

        Args:
            state: 协商状态
        """
        session_dir = self.data_dir / state.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_file = session_dir / f"checkpoint_{state.current_round:04d}.json"

        state_dict = state.to_dict()

        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, indent=2, ensure_ascii=False)

        print(f"💾 检查点已保存: {checkpoint_file.name}")

    async def save_final_state(self, state: NegotiationState):
        """
        保存最终状态

        Args:
            state: 协商状态
        """
        session_dir = self.data_dir / state.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        final_file = session_dir / "final_state.json"

        state_dict = state.to_dict()

        with open(final_file, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, indent=2, ensure_ascii=False)

    async def load_state(self, session_id: str) -> Optional[NegotiationState]:
        """
        加载协商状态

        Args:
            session_id: 会话 ID

        Returns:
            协商状态，如果不存在返回 None
        """
        session_dir = self.data_dir / session_id

        if not session_dir.exists():
            return None

        # 优先加载最终状态
        final_file = session_dir / "final_state.json"
        if final_file.exists():
            with open(final_file, 'r', encoding='utf-8') as f:
                state_dict = json.load(f)
            return NegotiationState.from_dict(state_dict)

        # 否则加载最新的检查点
        return await self.load_latest_checkpoint(session_id)

    async def load_checkpoint(
        self,
        session_id: str,
        round_id: int
    ) -> Optional[NegotiationState]:
        """
        加载特定检查点

        Args:
            session_id: 会话 ID
            round_id: 轮次 ID

        Returns:
            协商状态，如果不存在返回 None
        """
        session_dir = self.data_dir / session_id

        if not session_dir.exists():
            return None

        checkpoint_file = session_dir / f"checkpoint_{round_id:04d}.json"

        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            state_dict = json.load(f)

        return NegotiationState.from_dict(state_dict)

    async def load_latest_checkpoint(
        self,
        session_id: str
    ) -> Optional[NegotiationState]:
        """
        加载最新的检查点

        Args:
            session_id: 会话 ID

        Returns:
            协商状态，如果不存在返回 None
        """
        session_dir = self.data_dir / session_id

        if not session_dir.exists():
            return None

        # 查找所有检查点文件
        checkpoint_files = list(session_dir.glob("checkpoint_*.json"))

        if not checkpoint_files:
            return None

        # 按文件名排序，取最新的
        checkpoint_files.sort()
        latest_file = checkpoint_files[-1]

        with open(latest_file, 'r', encoding='utf-8') as f:
            state_dict = json.load(f)

        return NegotiationState.from_dict(state_dict)

    def list_sessions(self) -> List[dict]:
        """
        列出所有会话

        Returns:
            会话信息列表
        """
        sessions = []

        if not self.data_dir.exists():
            return sessions

        for session_dir in self.data_dir.iterdir():
            if not session_dir.is_dir():
                continue

            session_info = {
                "session_id": session_dir.name,
                "path": str(session_dir),
            }

            # 检查最终状态
            final_file = session_dir / "final_state.json"
            if final_file.exists():
                session_info["has_final_state"] = True
                session_info["final_state_time"] = datetime.fromtimestamp(
                    final_file.stat().st_mtime
                ).isoformat()
            else:
                session_info["has_final_state"] = False

            # 统计检查点数量
            checkpoint_files = list(session_dir.glob("checkpoint_*.json"))
            session_info["checkpoint_count"] = len(checkpoint_files)

            sessions.append(session_info)

        # 按时间排序
        sessions.sort(
            key=lambda x: x.get("final_state_time", ""),
            reverse=True
        )

        return sessions

    def cleanup_old_sessions(self, days: int = 30):
        """
        清理旧会话

        Args:
            days: 保留天数
        """
        if not self.data_dir.exists():
            return

        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)

        for session_dir in self.data_dir.iterdir():
            if not session_dir.is_dir():
                continue

            # 检查最后修改时间
            mtime = session_dir.stat().st_mtime

            if mtime < cutoff_time:
                # 删除整个会话目录
                import shutil
                shutil.rmtree(session_dir)
                print(f"🗑️  已删除旧会话: {session_dir.name}")

    def get_session_summary(self, session_id: str) -> Optional[dict]:
        """
        获取会话摘要

        Args:
            session_id: 会话 ID

        Returns:
            会话摘要，如果不存在返回 None
        """
        session_dir = self.data_dir / session_id

        if not session_dir.exists():
            return None

        summary = {
            "session_id": session_id,
            "path": str(session_dir),
        }

        # 读取最终状态
        final_file = session_dir / "final_state.json"
        if final_file.exists():
            with open(final_file, 'r', encoding='utf-8') as f:
                state_dict = json.load(f)

            summary["status"] = state_dict.get("status")
            summary["total_rounds"] = state_dict.get("current_round")
            summary["start_time"] = state_dict.get("start_time")
            summary["end_time"] = state_dict.get("end_time")
            summary["total_duration"] = state_dict.get("total_duration")

            # Pareto 前沿大小
            pareto_front = state_dict.get("pareto_front", [])
            summary["pareto_front_size"] = len(pareto_front)

            # 最终指标
            current_metrics = state_dict.get("current_metrics")
            if current_metrics:
                summary["final_area"] = current_metrics.get("area")
                summary["final_delay"] = current_metrics.get("delay")

        return summary

    def export_pareto_front(
        self,
        session_id: str,
        output_file: Optional[str] = None
    ) -> Optional[str]:
        """
        导出 Pareto 前沿到 CSV

        Args:
            session_id: 会话 ID
            output_file: 输出文件路径，默认为 session_dir/pareto_front.csv

        Returns:
            输出文件路径，如果失败返回 None
        """
        session_dir = self.data_dir / session_id

        if not session_dir.exists():
            return None

        # 读取最终状态
        final_file = session_dir / "final_state.json"
        if not final_file.exists():
            return None

        with open(final_file, 'r', encoding='utf-8') as f:
            state_dict = json.load(f)

        pareto_front = state_dict.get("pareto_front", [])

        if not pareto_front:
            return None

        # 确定输出文件
        if output_file:
            output_path = Path(output_file)
        else:
            output_path = session_dir / "pareto_front.csv"

        # 写入 CSV
        with open(output_path, 'w', encoding='utf-8') as f:
            # 表头
            f.write("area,delay,power,node_count,edge_count,levels\n")

            # 数据行
            for metrics in pareto_front:
                f.write(
                    f"{metrics['area']},"
                    f"{metrics['delay']},"
                    f"{metrics.get('power', '')},"
                    f"{metrics.get('node_count', '')},"
                    f"{metrics.get('edge_count', '')},"
                    f"{metrics.get('levels', '')}\n"
                )

        return str(output_path)
