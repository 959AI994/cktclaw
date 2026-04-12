"""
Small helpers shared by CktMem storage and examples.
"""

from typing import List, Dict, Any
from datetime import datetime
import json


def format_timestamp(dt: datetime) -> str:
    """Format ``datetime`` for logs / UI."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def truncate_text(text: str, max_length: int = 100) -> str:
    """Ellipsize long strings."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def estimate_text_tokens(text: str) -> int:
    """Heuristic token estimate (~4 chars per token)."""
    return len(text) // 4


def serialize_metadata(metadata: Dict[str, Any]) -> str:
    """JSON encode metadata for sqlite."""
    return json.dumps(metadata, ensure_ascii=False)


def deserialize_metadata(metadata_str: str) -> Dict[str, Any]:
    """JSON decode metadata from sqlite."""
    if not metadata_str:
        return {}
    return json.loads(metadata_str)


def format_verilog_code(code: str) -> str:
    """Wrap Verilog in a fenced markdown block."""
    return f"```verilog\n{code}\n```"


def extract_user_questions(messages: List) -> List[str]:
    """Collect plain-text user turns."""
    questions = []
    for msg in messages:
        if msg.role.value == "user":
            questions.append(msg.content)
    return questions


def calculate_compression_ratio(
    pre_tokens: int,
    post_tokens: int,
) -> float:
    """Percent tokens removed (0 when ``pre_tokens`` is zero)."""
    if pre_tokens == 0:
        return 0.0
    return (pre_tokens - post_tokens) / pre_tokens * 100
