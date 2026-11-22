"""CLI bridge so verilog-generator command provider can call CktClaw LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(
    r"^```(?P<info>[^\n`]*)\n(?P<content>.*?)(?:\n)?^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_PATH_LINE_RE = re.compile(
    r"^\s*(?://\s*|#\s*)?(?:path|filepath)[:=]\s*(?P<path>[^\s#]+)\s*(?:\n|$)",
    re.IGNORECASE,
)
_RTL_TB_COMMENT_PATH_RE = re.compile(
    r"^\s*(?://\s*)?(?:(?:path|filepath)[:=]\s*)?(?P<path>(?:rtl|tb)/[^\s#]+\.v)\s*$",
    re.IGNORECASE,
)
_HEX_JSON_NUMBER_RE = re.compile(r"0[xX]([0-9a-fA-F]+)(?=\s*[,}\]])")


def _path_from_fence_info(info: str) -> str | None:
    for token in info.split():
        if token.startswith("path="):
            return token.split("=", 1)[1].strip("\"'")
        if token.startswith("filepath="):
            return token.split("=", 1)[1].strip("\"'")
    return None


def _is_manifest_json_block(info: str, content: str) -> bool:
    language = info.split(maxsplit=1)[0].lower() if info else ""
    if language != "json" or _path_from_fence_info(info):
        return False
    try:
        candidate = json.loads(content)
    except json.JSONDecodeError:
        return False
    return isinstance(candidate, dict) and isinstance(candidate.get("files"), list)


def _sanitize_json_fence_content(content: str) -> str:
    """Strip # comments and hex literals so verilog-generator audit_vectors can parse JSON."""
    lines = [line for line in content.splitlines() if not line.lstrip().startswith("#")]
    text = "\n".join(lines).strip()
    if not text:
        return content
    text = _HEX_JSON_NUMBER_RE.sub(lambda match: str(int(match.group(1), 16)), text)
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return content
    return text


def _format_fence_block(info: str, content: str) -> str:
    language = info.split(maxsplit=1)[0].lower() if info else ""
    if _path_from_fence_info(info) and language == "json" and not _is_manifest_json_block(info, content):
        content = _sanitize_json_fence_content(content)
    return f"```{info}\n{content.rstrip()}\n```"


def _manifest_dict_from_text(text: str) -> dict | None:
    for match in _FENCE_RE.finditer(text):
        info = match.group("info").strip()
        if _path_from_fence_info(info):
            continue
        language = info.split(maxsplit=1)[0].lower() if info else ""
        if language != "json":
            continue
        try:
            candidate = json.loads(match.group("content"))
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("files"), list):
            return candidate
    return None


def _fenced_rel_paths(text: str) -> set[str]:
    paths: set[str] = set()
    for match in _FENCE_RE.finditer(text):
        rel_path = _path_from_fence_info(match.group("info").strip())
        if rel_path:
            paths.add(rel_path.replace("\\", "/"))
    return paths


def _language_for_rel_path(rel_path: str) -> str:
    lowered = rel_path.lower()
    if lowered.endswith(".json"):
        return "json"
    if lowered.endswith(".py"):
        return "python"
    if lowered.endswith((".v", ".sv")):
        return "verilog"
    return "text"


def _find_asset_on_disk(rel_path: str, search_roots: list[Path]) -> Path | None:
    rel = rel_path.replace("\\", "/")
    name = Path(rel).name
    for root in search_roots:
        if not root.is_dir():
            continue
        candidates = [root / rel, root / name]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        for hit in root.rglob(name):
            if hit.is_file() and hit.name == name:
                return hit
    return None


def _run_model_write_vectors(model_path: Path, vectors_rel: str) -> Path | None:
    rel = vectors_rel.replace("\\", "/")
    cwd = model_path.parent
    try:
        subprocess.run(
            [sys.executable, model_path.name, "write_vectors"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        logger.debug("model write_vectors failed for %s: %s", model_path, exc)
        return None
    for candidate in (cwd / rel, cwd / Path(rel).name, cwd / "model" / Path(rel).name):
        if candidate.is_file():
            return candidate
    return None


def inject_missing_manifest_fences(text: str, search_roots: list[Path]) -> tuple[str, list[str]]:
    """Inject fenced blocks for manifest paths missing from an LLM stage response."""
    manifest = _manifest_dict_from_text(text)
    if not manifest:
        return text, []

    fenced = _fenced_rel_paths(text)
    additions: list[str] = []
    injected: list[str] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        rel_path = str(entry.get("path", "")).replace("\\", "/").strip()
        if not rel_path or rel_path in fenced:
            continue

        asset = _find_asset_on_disk(rel_path, search_roots)
        if asset is None and rel_path.endswith("_vectors.json"):
            for root in search_roots:
                if not root.is_dir():
                    continue
                for model_path in sorted(root.rglob("*_model.py")):
                    asset = _run_model_write_vectors(model_path, rel_path)
                    if asset is not None:
                        break
                if asset is not None:
                    break
        if asset is None:
            continue

        language = _language_for_rel_path(rel_path)
        additions.append(_format_fence_block(f"{language} path={rel_path}", asset.read_text(encoding="utf-8")))
        injected.append(rel_path)

    if not additions:
        return text, injected
    return text.rstrip() + "\n\n" + "\n\n".join(additions) + "\n", injected


def patch_workflow_python_responses(workflow_dir: Path) -> list[str]:
    """Patch saved python stage responses with missing manifest fences."""
    patched: list[str] = []
    for response_path in sorted(workflow_dir.glob("attempt-*/python/python_response.md")):
        attempt_dir = response_path.parent
        search_roots = [
            attempt_dir / "generated",
            attempt_dir / "generated" / "model",
            attempt_dir,
            workflow_dir,
        ]
        try:
            text = response_path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text, injected = inject_missing_manifest_fences(text, search_roots)
        if not injected:
            continue
        normalized = normalize_verilog_generator_response(new_text)
        response_path.write_text(normalized, encoding="utf-8")
        patched.extend(injected)
    return patched


def _comment_path_from_content(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _RTL_TB_COMMENT_PATH_RE.match(stripped)
        if match:
            return match.group("path").replace("\\", "/")
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        break
    return None


def _strip_leading_comment_path(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return content
    if _RTL_TB_COMMENT_PATH_RE.match(lines[0].strip()) or _PATH_LINE_RE.match(lines[0]):
        return "\n".join(lines[1:]).lstrip("\n")
    return content


def patch_workflow_rtl_responses(workflow_dir: Path) -> list[str]:
    """Normalize RTL stage responses so bare ```verilog fences gain path= info."""
    patched: list[str] = []
    for response_path in sorted(workflow_dir.glob("attempt-*/rtl/rtl_response.md")):
        try:
            text = response_path.read_text(encoding="utf-8")
        except OSError:
            continue
        normalized = normalize_verilog_generator_response(text)
        if normalized == text:
            continue
        response_path.write_text(normalized, encoding="utf-8")
        for match in _FENCE_RE.finditer(normalized):
            rel_path = _path_from_fence_info(match.group("info").strip())
            if rel_path:
                patched.append(rel_path)
    return patched


def normalize_verilog_generator_response(text: str) -> str:
    """Fix common LLM fence mistakes so verilog-generator extractor can parse output."""
    parts: list[str] = []
    cursor = 0
    for match in _FENCE_RE.finditer(text):
        parts.append(text[cursor:match.start()])
        info = match.group("info").strip()
        content = match.group("content")
        if _path_from_fence_info(info) or _is_manifest_json_block(info, content):
            parts.append(_format_fence_block(info, content))
        else:
            path_match = _PATH_LINE_RE.match(content)
            comment_path = _comment_path_from_content(content)
            if path_match:
                rel_path = path_match.group("path").strip()
                language = info.split(maxsplit=1)[0] if info else "text"
                rest = content[path_match.end():]
                parts.append(_format_fence_block(f"{language} path={rel_path}", rest))
            elif comment_path:
                language = info.split(maxsplit=1)[0] if info else "verilog"
                rest = _strip_leading_comment_path(content)
                parts.append(_format_fence_block(f"{language} path={comment_path}", rest))
            else:
                parts.append(match.group(0))
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts)


def extract_fenced_files_to_directory(text: str, dest_root: Path) -> list[str]:
    """Normalize LLM response and write path= fenced files under dest_root."""
    normalized = normalize_verilog_generator_response(text)
    written: list[str] = []
    for match in _FENCE_RE.finditer(normalized):
        info = match.group("info").strip()
        rel_path = _path_from_fence_info(info)
        content = match.group("content")
        if not rel_path:
            path_match = _PATH_LINE_RE.match(content)
            if path_match:
                rel_path = path_match.group("path").strip()
                content = content[path_match.end():]
        if not rel_path:
            continue
        dest = dest_root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content.rstrip() + "\n", encoding="utf-8")
        written.append(str(dest))
    return written


def _read_prompt() -> str:
    prompt_path = os.environ.get("VERILOG_GEN_PROMPT_PATH", "").strip()
    if prompt_path and Path(prompt_path).is_file():
        return Path(prompt_path).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


async def _generate(prompt: str) -> str:
    from cktclaw.llm.base import ChatMessage
    from cktclaw.llm.router import get_model_router
    from cktclaw.llm.types import MessageRole

    router = get_model_router()
    provider = router.current_provider
    if provider is None:
        raise RuntimeError("No LLM provider configured in CktClaw.")

    messages = [ChatMessage(role=MessageRole.USER, content=prompt)]
    max_tokens = int(os.environ.get("CKTCLAW_RTL_LLM_MAX_TOKENS", "16384"))
    response = await provider.chat(messages, max_tokens=max_tokens)
    content = response.content if hasattr(response, "content") else str(response)
    content = normalize_verilog_generator_response(content)
    response_path = os.environ.get("VERILOG_GEN_RESPONSE_PATH", "").strip()
    if response_path:
        Path(response_path).write_text(content, encoding="utf-8")
    return content


def main() -> int:
    prompt = _read_prompt()
    if not prompt.strip():
        print("cktclaw_llm_bridge: empty prompt", file=sys.stderr)
        return 2
    try:
        text = asyncio.run(_generate(prompt))
    except Exception as exc:
        print(f"cktclaw_llm_bridge error: {exc}", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
