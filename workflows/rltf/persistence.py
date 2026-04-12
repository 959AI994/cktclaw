"""
RLTF Persistence - 持久化管理器

负责 RLTF 状态的保存、加载和检查点管理。
"""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from .types import RLTFState, RLTFResult


class RLTFPersistence:
    """
    RLTF 持久化管理器

    提供状态的保存、加载和检查点功能。
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        初始化持久化管理器

        Args:
            data_dir: 数据目录，默认为 data/rltf_sessions
        """
        if data_dir is None:
            # 默认数据目录
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data" / "rltf_sessions"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def save_checkpoint(self, state: RLTFState) -> str:
        """
        保存检查点

        Args:
            state: RLTF 状态

        Returns:
            检查点文件路径
        """
        checkpoint_file = self._get_checkpoint_path(
            state.session_id,
            state.current_iteration
        )

        # 转换为字典
        state_dict = state.to_dict()

        # 保存为 JSON
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, indent=2, ensure_ascii=False)

        return str(checkpoint_file)

    async def load_checkpoint(self, session_id: str, iteration: Optional[int] = None) -> Optional[RLTFState]:
        """
        加载检查点

        Args:
            session_id: 会话 ID
            iteration: 迭代次数，如果为 None 则加载最新的检查点

        Returns:
            RLTF 状态，如果不存在则返回 None
        """
        if iteration is None:
            # 查找最新的检查点
            checkpoint_file = self._find_latest_checkpoint(session_id)
        else:
            checkpoint_file = self._get_checkpoint_path(session_id, iteration)

        if not checkpoint_file or not checkpoint_file.exists():
            return None

        # 从 JSON 加载
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                state_dict = json.load(f)

            # 转换为对象
            state = RLTFState.from_dict(state_dict)
            return state

        except Exception as e:
            print(f"Failed to load checkpoint: {e}")
            return None

    async def save_final_state(self, state: RLTFState) -> str:
        """
        保存最终状态

        Args:
            state: RLTF 状态

        Returns:
            状态文件路径
        """
        state_file = self._get_state_path(state.session_id)

        # 转换为字典
        state_dict = state.to_dict()

        # 保存为 JSON
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, indent=2, ensure_ascii=False)

        return str(state_file)

    async def load_state(self, session_id: str) -> Optional[RLTFState]:
        """
        加载最终状态

        Args:
            session_id: 会话 ID

        Returns:
            RLTF 状态，如果不存在则返回 None
        """
        state_file = self._get_state_path(session_id)

        if not state_file.exists():
            return None

        # 从 JSON 加载
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_dict = json.load(f)

            # 转换为对象
            state = RLTFState.from_dict(state_dict)
            return state

        except Exception as e:
            print(f"Failed to load state: {e}")
            return None

    async def save_result(self, result: RLTFResult) -> str:
        """
        保存最终结果

        Args:
            result: RLTF 结果

        Returns:
            结果文件路径
        """
        result_file = self._get_result_path(result.state.session_id)

        # 转换为字典
        result_dict = result.to_dict()

        # 保存为 JSON
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        return str(result_file)

    async def load_result(self, session_id: str) -> Optional[RLTFResult]:
        """
        加载最终结果

        Args:
            session_id: 会话 ID

        Returns:
            RLTF 结果，如果不存在则返回 None
        """
        result_file = self._get_result_path(session_id)

        if not result_file.exists():
            return None

        # 从 JSON 加载
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result_dict = json.load(f)

            # 转换为对象
            result = RLTFResult.from_dict(result_dict)
            return result

        except Exception as e:
            print(f"Failed to load result: {e}")
            return None

    def list_sessions(self) -> list[str]:
        """
        列出所有会话

        Returns:
            会话 ID 列表
        """
        sessions = []

        for item in self.data_dir.iterdir():
            if item.is_dir() and item.name.startswith("rltf_"):
                sessions.append(item.name)

        return sorted(sessions)

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """
        获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            会话信息字典，如果不存在则返回 None
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            return None

        # 统计检查点数量
        checkpoint_count = len(list(session_dir.glob("checkpoint_*.json")))

        # 检查是否有最终状态
        has_final_state = self._get_state_path(session_id).exists()
        has_result = self._get_result_path(session_id).exists()

        # 获取创建时间
        created_time = datetime.fromtimestamp(session_dir.stat().st_ctime)

        return {
            "session_id": session_id,
            "checkpoint_count": checkpoint_count,
            "has_final_state": has_final_state,
            "has_result": has_result,
            "created_time": created_time.isoformat(),
        }

    def cleanup_session(self, session_id: str) -> bool:
        """
        清理会话数据

        Args:
            session_id: 会话 ID

        Returns:
            是否成功
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            return False

        try:
            # 删除所有文件
            for file in session_dir.iterdir():
                if file.is_file():
                    file.unlink()

            # 删除目录
            session_dir.rmdir()
            return True

        except Exception as e:
            print(f"Failed to cleanup session: {e}")
            return False

    def cleanup_old_checkpoints(self, session_id: str, keep_count: int = 5) -> int:
        """
        清理旧的检查点，只保留最新的 N 个

        Args:
            session_id: 会话 ID
            keep_count: 保留的检查点数量

        Returns:
            删除的检查点数量
        """
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            return 0

        # 获取所有检查点文件
        checkpoints = sorted(
            session_dir.glob("checkpoint_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # 删除旧的检查点
        deleted_count = 0
        for checkpoint in checkpoints[keep_count:]:
            try:
                checkpoint.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete checkpoint {checkpoint}: {e}")

        return deleted_count

    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话目录"""
        return self.data_dir / session_id

    def _get_checkpoint_path(self, session_id: str, iteration: int) -> Path:
        """获取检查点文件路径"""
        session_dir = self._get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / f"checkpoint_{iteration:04d}.json"

    def _get_state_path(self, session_id: str) -> Path:
        """获取状态文件路径"""
        session_dir = self._get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "state.json"

    def _get_result_path(self, session_id: str) -> Path:
        """获取结果文件路径"""
        session_dir = self._get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "result.json"

    def _find_latest_checkpoint(self, session_id: str) -> Optional[Path]:
        """查找最新的检查点"""
        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            return None

        # 获取所有检查点文件
        checkpoints = sorted(
            session_dir.glob("checkpoint_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        return checkpoints[0] if checkpoints else None
