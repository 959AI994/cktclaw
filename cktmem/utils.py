"""
工具函数
"""

from typing import List, Dict, Any
from datetime import datetime
import json


def format_timestamp(dt: datetime) -> str:
    """格式化时间戳"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def estimate_text_tokens(text: str) -> int:
    """粗估文本 token 数（1 token ≈ 4 chars）"""
    return len(text) // 4


def serialize_metadata(metadata: Dict[str, Any]) -> str:
    """序列化元数据"""
    return json.dumps(metadata, ensure_ascii=False)


def deserialize_metadata(metadata_str: str) -> Dict[str, Any]:
    """反序列化元数据"""
    if not metadata_str:
        return {}
    return json.loads(metadata_str)


def format_verilog_code(code: str) -> str:
    """格式化 Verilog 代码"""
    return f"```verilog\n{code}\n```"


def extract_user_questions(messages: List) -> List[str]:
    """提取用户问题"""
    questions = []
    for msg in messages:
        if msg.role.value == "user":
            questions.append(msg.content)
    return questions


def calculate_compression_ratio(
    pre_tokens: int,
    post_tokens: int,
) -> float:
    """计算压缩比"""
    if pre_tokens == 0:
        return 0.0
    return (pre_tokens - post_tokens) / pre_tokens * 100
