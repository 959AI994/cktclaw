"""Web upload storage and attachment context building."""

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_SESSION = 50
MAX_INLINE_CHARS = 8000

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
TEXT_EXTENSIONS = {
    "v", "sv", "vh", "svh", "py", "md", "txt", "json", "yml", "yaml",
    "tcl", "sdc", "lib", "lef", "def", "spice", "csv", "log",
}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | TEXT_EXTENSIONS

_SAFE_SESSION_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _home_root() -> Path:
    home = os.environ.get("CKTCLAW_HOME")
    if home:
        return Path(home)
    return Path.cwd() / ".cktclaw"


def _sanitize_session_id(session_id: str) -> str:
    sid = (session_id or "default").strip()
    sid = _SAFE_SESSION_RE.sub("_", sid)
    return sid[:128] or "default"


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-]", "_", base)
    return base[:200] or "file"


def _uploads_root(session_id: str) -> Path:
    return _home_root() / "web-uploads" / _sanitize_session_id(session_id)


@dataclass
class UploadMeta:
    id: str
    filename: str
    path: str
    mime: str
    size: int
    session_id: str

    def to_dict(self) -> dict:
        sid = _sanitize_session_id(self.session_id)
        return {
            "id": self.id,
            "filename": self.filename,
            "path": self.path,
            "mime": self.mime,
            "size": self.size,
            "session_id": sid,
            "url": f"/api/uploads/{self.id}?session_id={sid}",
        }


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type '.{ext}' not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return ext


def _count_session_files(session_id: str) -> int:
    root = _uploads_root(session_id)
    if not root.is_dir():
        return 0
    return sum(1 for p in root.iterdir() if p.is_file())


def _find_file_by_id(session_id: str, upload_id: str) -> Optional[Path]:
    root = _uploads_root(session_id)
    if not root.is_dir():
        return None
    prefix = f"{upload_id}_"
    for p in root.iterdir():
        if p.is_file() and p.name.startswith(prefix):
            return p
    return None


async def save_upload(session_id: str, file) -> UploadMeta:
    """Save an uploaded file from FastAPI UploadFile."""
    sid = _sanitize_session_id(session_id)
    if _count_session_files(sid) >= MAX_FILES_PER_SESSION:
        raise ValueError(f"Max {MAX_FILES_PER_SESSION} files per session reached")

    original = file.filename or "file"
    _validate_extension(original)
    safe_name = _sanitize_filename(original)

    content = await file.read()
    size = len(content)
    if size == 0:
        raise ValueError("Empty file")
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File exceeds max size ({MAX_FILE_SIZE // (1024 * 1024)} MB)")

    upload_id = uuid.uuid4().hex[:8]
    root = _uploads_root(sid)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{upload_id}_{safe_name}"
    dest.write_bytes(content)

    mime = file.content_type or _guess_mime(safe_name)
    return UploadMeta(
        id=upload_id,
        filename=safe_name,
        path=str(dest.resolve()),
        mime=mime,
        size=size,
        session_id=sid,
    )


def get_upload(session_id: str, upload_id: str) -> Optional[UploadMeta]:
    sid = _sanitize_session_id(session_id)
    path = _find_file_by_id(sid, upload_id)
    if path is None:
        return None
    stat = path.stat()
    name = path.name.split("_", 1)[-1] if "_" in path.name else path.name
    return UploadMeta(
        id=upload_id,
        filename=name,
        path=str(path.resolve()),
        mime=_guess_mime(name),
        size=stat.st_size,
        session_id=sid,
    )


def list_uploads(session_id: str) -> List[UploadMeta]:
    sid = _sanitize_session_id(session_id)
    root = _uploads_root(sid)
    if not root.is_dir():
        return []
    result: List[UploadMeta] = []
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        parts = p.name.split("_", 1)
        if len(parts) != 2:
            continue
        upload_id, name = parts
        result.append(UploadMeta(
            id=upload_id,
            filename=name,
            path=str(p.resolve()),
            mime=_guess_mime(name),
            size=p.stat().st_size,
            session_id=sid,
        ))
    return result


def delete_upload(session_id: str, upload_id: str) -> bool:
    sid = _sanitize_session_id(session_id)
    path = _find_file_by_id(sid, upload_id)
    if path is None:
        return False
    path.unlink(missing_ok=True)
    return True


def resolve_uploads(session_id: str, attachment_ids: Optional[List[str]]) -> List[UploadMeta]:
    if not attachment_ids:
        return []
    sid = _sanitize_session_id(session_id)
    result: List[UploadMeta] = []
    for uid in attachment_ids:
        meta = get_upload(sid, uid.strip())
        if meta:
            result.append(meta)
    return result


def build_attachment_context(
    uploads: List[UploadMeta],
    max_inline_chars: int = MAX_INLINE_CHARS,
) -> str:
    if not uploads:
        return ""

    lines = ["", "---", "## Attachments"]
    for meta in uploads:
        ext = Path(meta.filename).suffix.lstrip(".").lower()
        lines.append(f"\n### {meta.filename}")
        lines.append(f"- Path: `{meta.path}`")
        lines.append(f"- Type: {meta.mime} ({meta.size} bytes)")

        if ext in IMAGE_EXTENSIONS:
            lines.append("- Note: Image uploaded (path reference only; vision not enabled).")
            continue

        if ext in TEXT_EXTENSIONS:
            try:
                text = Path(meta.path).read_text(encoding="utf-8", errors="replace")
                if len(text) > max_inline_chars:
                    line_count = text.count("\n") + 1
                    text = text[:max_inline_chars] + f"\n... (truncated, {line_count} lines total)"
                lines.append(f"\n```\n{text}\n```")
            except OSError as e:
                lines.append(f"- Error reading file: {e}")

    return "\n".join(lines)
