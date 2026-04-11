"""
Chat Handler - Multi-turn conversation

Handles regular text input (non-slash commands) for multi-turn conversation.
Features:
- Assembles context from long + short memory
- Calls LLM analyzer with full context
- Complete result rendering (no streaming)
- Stores messages in memory for future context
"""

import time
import asyncio
import shlex
import subprocess
import json
import re
import io
import os
from pathlib import Path
from typing import Optional
from rich.console import Console

from ..ui import (
    render_spinner,
    render_error,
    render_user_message,
    render_assistant_message,
    render_completion_summary,
    format_time,
    Icons,
)

try:
    from cktclaw.models import LLMVerilogAnalyzer
except ImportError as e:
    raise ImportError(f"Failed to import LLMVerilogAnalyzer: {e}")


async def process_chat(user_message: str, cli_state) -> None:
    """
    Handle multi-turn chat message.

    Workflow:
    1. Assemble context from long + short memory
    2. Call LLM with full context
    3. Wait for complete response
    4. Store user message + response in memory
    5. Render markdown report + timing info

    Args:
        user_message: User's text input
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    # ━━━━━━━━━━ 1. Previous strict context check removed ━━━━━━━━━━
    # Now chat is allowed without prior /reverse step. The model will
    # leverage session memory (including EDA tool outputs) as context.

    # ━━━━━━━━━━ 2. Assemble context (using cktmem) ━━━━━━━━━━
    try:
        # Use cktmem ContextManager to build context with auto-compression
        messages = await cli_state.context_manager.build_context(
            session_id=cli_state.session_id,
            user_message=user_message,
            auto_compact=True,  # Enable automatic compression
        )

        # Convert cktmem Message objects to dict format for LLM
        messages = [
            {
                "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]
    except Exception as e:
        render_error(
            console,
            f"Failed to build context: {e}",
            error_type="error",
        )
        return

    # ━━━━━━━━━━ 3. Call LLM ━━━━━━━━━━
    start_time = time.time()

    with render_spinner(
        console,
        f"{Icons.CIRCUIT} Analyzing with {cli_state.current_engine}...",
    ):
        try:
            # Lazy-load LLM analyzer if needed (verbose=False: 不输出 GPU/模型加载日志)
            if cli_state.llm_analyzer is None:
                cli_state.llm_analyzer = LLMVerilogAnalyzer(verbose=False)

            # Agent loop: keep calling model until no tool_call is returned.
            working_messages = list(messages)
            response = ""
            max_steps = 5
            MAX_RETRIES = 3
            for step in range(max_steps):
                llm_resp = await asyncio.to_thread(
                    _chat_with_messages,
                    cli_state.llm_analyzer,
                    working_messages,
                    cli_state.current_engine,
                )

                response_text = llm_resp if isinstance(llm_resp, str) else _to_memory_text(llm_resp)
                command_to_execute = None
                tool_call_id = f"content_call_{step + 1}"

                # Native tool-call object from API/analyzer
                if isinstance(llm_resp, dict) and llm_resp.get("type") == "tool_call":
                    tool_call_id = str(llm_resp.get("tool_call_id") or f"dict_call_{step + 1}")
                    if llm_resp.get("name") == "execute_cktclaw_command":
                        command_to_execute = str((llm_resp.get("arguments") or {}).get("command", "")).strip() or None
                else:
                    # Plain-text tool-call JSON emitted by local model
                    command_to_execute = _extract_tool_call_command(response_text)
                    # Secondary fallback: reuse analyzer-side robust parser if available
                    if not command_to_execute and hasattr(cli_state.llm_analyzer, "_extract_local_tool_call"):
                        try:
                            parsed = cli_state.llm_analyzer._extract_local_tool_call(response_text)
                            if isinstance(parsed, dict) and parsed.get("type") == "tool_call":
                                if parsed.get("name") == "execute_cktclaw_command":
                                    tool_call_id = str(parsed.get("tool_call_id") or f"parser_call_{step + 1}")
                                    command_to_execute = str((parsed.get("arguments") or {}).get("command", "")).strip() or None
                        except Exception:
                            pass

                # If a tool call is detected, execute and feed tool output back into messages.
                if command_to_execute:
                    attempt = 0
                    tool_output = ""
                    final_command = command_to_execute
                    success = False
                    return_code = -1
                    while attempt < MAX_RETRIES:
                        with render_spinner(
                            console,
                            "⏳ CktClaw Agent is executing the command...",
                        ):
                            tool_output = await asyncio.to_thread(
                                execute_cktclaw_command,
                                final_command,
                                cli_state,
                            )
                        console.print(
                            f"[dim]🔧 Agent 尝试执行: {final_command} -> 结果长度: {len(tool_output or '')}[/dim]"
                        )

                        success, return_code = _parse_tool_status(tool_output, final_command)
                        if success and return_code == 0:
                            break

                        attempt += 1
                        if attempt >= MAX_RETRIES:
                            break

                        console.print(
                            f"[dim]- 执行失败，Agent 正在进行第 {attempt} 次反思与重试...[/dim]"
                        )
                        error_feedback = (
                            "TOOL EXECUTION FAILED.\n"
                            f"Command: {final_command}\n"
                            f"Error Output:\n{tool_output}\n\n"
                            "Please analyze this error. If it is a syntax/argument issue, output a corrected "
                            "TOOL_CALL for execute_cktclaw_command. If a required file/path is missing, stop and ask user."
                        )
                        reflex_messages = list(working_messages)
                        reflex_messages.append({"role": "user", "content": error_feedback})
                        new_resp = await asyncio.to_thread(
                            _chat_with_messages,
                            cli_state.llm_analyzer,
                            reflex_messages,
                            cli_state.current_engine,
                        )
                        new_text = new_resp if isinstance(new_resp, str) else _to_memory_text(new_resp)
                        new_command = None
                        if isinstance(new_resp, dict) and new_resp.get("type") == "tool_call":
                            if new_resp.get("name") == "execute_cktclaw_command":
                                new_command = str((new_resp.get("arguments") or {}).get("command", "")).strip() or None
                        if not new_command:
                            new_command = _extract_tool_call_command(new_text)
                        if not new_command and hasattr(cli_state.llm_analyzer, "_extract_local_tool_call"):
                            try:
                                parsed = cli_state.llm_analyzer._extract_local_tool_call(new_text)
                                if isinstance(parsed, dict) and parsed.get("type") == "tool_call":
                                    if parsed.get("name") == "execute_cktclaw_command":
                                        new_command = str((parsed.get("arguments") or {}).get("command", "")).strip() or None
                            except Exception:
                                pass
                        if not new_command:
                            response = (
                                "工具执行失败，Agent 在反思后未能生成可用修复命令。\n\n"
                                f"最后命令:\n`{final_command}`\n\n"
                                f"错误摘要:\n{_compact_tool_output(tool_output)}"
                            )
                            break
                        final_command = new_command

                    if response:
                        break
                    if not (success and return_code == 0):
                        response = (
                            "工具调用在多次反思重试后仍失败，已停止自动重试。\n\n"
                            f"最后命令:\n`{final_command}`\n\n"
                            f"错误摘要:\n{_compact_tool_output(tool_output)}\n\n"
                            "建议：请检查输入路径/参数，或改用其他工具链。"
                        )
                        break

                    working_messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": "execute_cktclaw_command",
                                    "arguments": json.dumps({"command": final_command}, ensure_ascii=False),
                                },
                            }
                        ],
                    })
                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": "execute_cktclaw_command",
                        "content": _to_memory_text(tool_output),
                    })

                    # Local model may keep emitting tool_call forever.
                    # Force deterministic summary after one successful execution.
                    if cli_state.current_engine == "local":
                        response = _build_local_tool_summary(final_command, tool_output)
                        break

                    # Continue loop: ask cloud model again to summarize tool output.
                    continue

                # No tool call => final user-visible assistant message.
                response = response_text
                break
            else:
                # Loop exhausted without final natural-language answer
                response = "Agent reached tool-calling step limit without producing a final summary."

            if not response:
                render_error(
                    console,
                    "LLM returned empty response",
                    error_type="error",
                )
                return

            elapsed = time.time() - start_time

        except Exception as e:
            render_error(
                console,
                f"Analysis error: {e}",
                error_type="error",
            )
            return

    # ━━━━━━━━━━ 4. Store in memory (using cktmem) ━━━━━━━━━━
    try:
        user_content = _to_memory_text(user_message)
        assistant_content = _to_memory_text(response)

        # User message already added in build_context, only add assistant response
        await cli_state.context_manager.add_assistant_message(
            session_id=cli_state.session_id,
            content=assistant_content,
        )

        cli_state.chat_turns += 1
    except Exception as e:
        render_error(
            console,
            f"Failed to store in memory: {e}",
            error_type="error",
        )
        return

    # ━━━━━━━━━━ 5. Render output ━━━━━━━━━━
    console.print()
    render_user_message(console, user_content)
    console.print()
    render_assistant_message(console, assistant_content)
    console.print()

    # Timing summary
    timing_dict = {"response_generation": elapsed}
    render_completion_summary(console, timing_dict, title="Response Summary")
    console.print()


# ━━━━━━━━━━ Helper Functions ━━━━━━━━━━
def _chat_with_messages(
    llm_analyzer: LLMVerilogAnalyzer,
    messages: list,
    engine: str,
) -> Optional[object]:
    """
    Call LLM analyzer with assembled messages.

    Args:
        llm_analyzer: LLMVerilogAnalyzer instance
        messages: Assembled context messages
        engine: Engine choice ("deepseek" or "local")

    Returns:
        Response text from LLM
    """
    try:
        # Direct API call to analyzer's chat method
        # Adjust interface based on actual LLMVerilogAnalyzer implementation
        if hasattr(llm_analyzer, 'chat_with_context'):
            response = llm_analyzer.chat_with_context(messages, engine)
        elif hasattr(llm_analyzer, 'chat'):
            response = llm_analyzer.chat(messages, engine)
        else:
            # Fallback: call analyze method
            # (This may not be ideal but ensures compatibility)
            response = _analyze_with_context(llm_analyzer, messages, engine)

        return response

    except Exception as e:
        raise


def execute_cktclaw_command(command: str, cli_state) -> str:
    """
    Execute a CktClaw command for agent function-calling.
    Supports: ai4eda/cktclaw, abc, yosys, reverse.
    """
    from ..eda_tools import ABCRunner, YosysRunner
    from ..eda_tools.base_runner import clean_eda_output

    cmd = command.strip()
    # Hard branch for /reverse: auto-grounding + forced writeback + deterministic payload.
    if cmd.startswith("/reverse") or cmd.startswith("reverse"):
        parts = cmd.split()
        if len(parts) < 2:
            return "ERROR: Missing file path."

        aig_path = os.path.abspath(parts[1])
        v_path = aig_path.rsplit(".", 1)[0] + ".v"

        from .reverse_handler import process_reverse
        engine_raw_output = _run_reverse_silent(aig_path, cli_state, process_reverse)

        # Extract verilog text from raw engine output even when file is absent.
        code_match = re.search(r"module\s+.*?\s+endmodule", engine_raw_output, re.DOTALL | re.IGNORECASE)
        verilog_code = code_match.group(0) if code_match else ""

        # If a physical file exists, prefer filesystem truth.
        if os.path.exists(v_path):
            try:
                with open(v_path, "r", encoding="utf-8") as f:
                    verilog_raw = f.read()
                verilog_code = _clean_verilog_line_numbers(verilog_raw)
                print(f"DEBUG: Read code length: {len(verilog_code)}")
                return (
                    "SUCCESS_VERIFIED\n"
                    f"FILE_PATH: {v_path}\n"
                    f"CODE_CONTENT_START\n{verilog_code}\nCODE_CONTENT_END"
                )
            except Exception as e:
                return f"ERROR: Generated file found at {v_path} but could not be read: {str(e)}"

        # No file, but code exists in output: force writeback to same directory.
        if verilog_code:
            try:
                verilog_code = _clean_verilog_line_numbers(verilog_code)
                with open(v_path, "w", encoding="utf-8") as f:
                    f.write(verilog_code)
                print(f"DEBUG: Read code length: {len(verilog_code)}")
                return (
                    "SUCCESS_VERIFIED\n"
                    f"FILE_PATH: {v_path}\n"
                    f"CODE_CONTENT_START\n{verilog_code}\nCODE_CONTENT_END"
                )
            except Exception as e:
                return f"ERROR: Verilog extracted but failed to write file at {v_path}: {str(e)}"

        return f"ERROR: Could not find Verilog code in engine output. Raw: {(engine_raw_output or '')[:200]}"

    # Command sanitization: avoid filename/semicolon sticking (e.g., file.aig;)
    # and normalize whitespace before parsing.
    if cmd:
        cmd = cmd.replace(";", " ; ")
        # Do NOT use plain split/join here, otherwise quoted payloads (e.g. -p '...') may break.
    if not cmd:
        return "Empty command"
    parts = shlex.split(cmd)
    if not parts:
        return "Empty command"

    root = parts[0].lstrip("/").lower()
    # Preserve raw argument string (with quoting semantics) for downstream runners.
    m = re.match(r"^\s*\S+(?:\s+(.*))?$", cmd)
    args_raw = (m.group(1) if m else "") or ""
    args_raw = args_raw.strip()

    if root in ("ai4eda", "cktclaw"):
        toolkit = "/home/wjx/pythonproject/AI4EDA-OpenABC-Data-Toolkit/ai4eda-toolkit"
        default_lib = "/home/wjx/pythonproject/AI4EDA-OpenABC-Data-Toolkit/libs/asap7.lib"
        parts = _normalize_ai4eda_command(parts, default_lib)
        proc = subprocess.run(
            [toolkit] + parts[1:],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        merged = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return f"[exit={proc.returncode}]\n{clean_eda_output('AI4EDA', merged) or merged or '(no output)'}"

    if root == "abc":
        result = ABCRunner().run(args_raw)
        merged = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        return f"[exit={result.returncode}]\n{clean_eda_output('ABC', merged) or merged or result.error or '(no output)'}"

    if root == "yosys":
        result = YosysRunner().run(args_raw)
        merged = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        return f"[exit={result.returncode}]\n{clean_eda_output('Yosys', merged) or merged or result.error or '(no output)'}"

    if root == "reverse":
        # Normalized "reverse <path>" path (without leading slash) fallback.
        if not args_raw:
            return "ERROR: Missing file path."
        hard_cmd = f"/reverse {args_raw}"
        return execute_cktclaw_command(hard_cmd, cli_state)

    return f"Unsupported command root: {root}"


def _to_memory_text(content) -> str:
    """Convert any message payload to SQLite-safe TEXT."""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _extract_tool_call_command(text: str) -> Optional[str]:
    """
    Stable extractor for tool-call JSON embedded in plain text.
    Uses first '{' + last '}' slicing to avoid nested-brace truncation.
    """
    if not text:
        return None
    text = text.strip()
    # 1) Fast guard
    if "execute_cktclaw_command" not in text:
        return None
    # 2) Find first '{' and last '}'
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return None
    json_str = text[start_idx:end_idx + 1]

    try:
        # 3) Parse full JSON
        tool_data = json.loads(json_str)
        # Ignore unrelated JSON objects
        tool_name = tool_data.get("name") or tool_data.get("tool_name")
        tool_type = tool_data.get("type")
        if tool_name not in ("execute_cktclaw_command",) and tool_type != "tool_call":
            return None
        # 4) Extract command
        args = tool_data.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                return None
        if isinstance(args, dict):
            command = args.get("command")
            if command:
                return str(command).strip()
    except Exception:
        # 解析失败不抛出，返回 None
        pass
    return None


def _build_local_tool_summary(command: str, tool_output: str) -> str:
    """
    Deterministic fallback summary for local model after executing a tool command.
    Prevents infinite tool-call loops.
    """
    lines = [ln.strip() for ln in (tool_output or "").splitlines() if ln.strip()]
    key_lines = []
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in ("area", "delay", "lev", "i/o", "and", "time", "warning", "error")):
            key_lines.append(ln)
    if not key_lines:
        key_lines = lines[:12]

    preview = "\n".join(key_lines).strip() if key_lines else "(no output)"
    return (
        "已完成工具执行并拿到结果。\n\n"
        f"执行命令:\n`{command}`\n\n"
        "关键输出:\n"
        f"{preview}\n\n"
        "说明: 本地模型在工具回注后可能持续发起重复 tool_call，"
        "系统已采用确定性总结避免循环。"
    )


def _normalize_ai4eda_command(parts: list[str], default_lib: str) -> list[str]:
    """
    Normalize frequently malformed agent-generated ai4eda commands into valid CLI form.
    Target CLI: ai4eda metrics <input> --lib <lib> [--abc-path ...] [--opt-script ...] [--batch]
    """
    if len(parts) < 2:
        return parts
    sub = parts[1].lower()
    # Map hallucinated/legacy subcommand to metrics
    if sub == "analyze":
        parts[1] = "metrics"
        sub = "metrics"

    if sub != "metrics":
        return parts

    rest = parts[2:]
    if not rest:
        return parts

    # Remove common hallucinated flags not supported by ai4eda metrics
    drop_flags = {"--area", "--delay", "-area", "-delay"}
    rest = [t for t in rest if t not in drop_flags]

    # Find the first plausible input file path token
    input_token = None
    for t in rest:
        if t.startswith("-"):
            continue
        if Path(t).exists() or t.endswith((".aig", ".bench")):
            input_token = t
            break

    # Capture existing --lib <path> pair if present
    existing_lib_flag: list[str] = []
    lib_is_valid = False
    if "--lib" in rest:
        try:
            lib_idx = rest.index("--lib")
            lib_val = rest[lib_idx + 1] if lib_idx + 1 < len(rest) else ""
            # 认为有效值需非空且不是下一个标志位
            if lib_val and not lib_val.startswith("-"):
                existing_lib_flag = ["--lib", lib_val]
                lib_is_valid = True
            else:
                # 移除悬空的 --lib，稍后用默认库补齐
                trimmed = []
                skip_next = False
                for i, tok in enumerate(rest):
                    if skip_next:
                        skip_next = False
                        continue
                    if tok == "--lib":
                        # 如果有下一个值但无效，也一起丢弃
                        if i + 1 < len(rest) and not rest[i + 1].startswith("-"):
                            skip_next = True
                        continue
                    trimmed.append(tok)
                rest = trimmed
        except ValueError:
            existing_lib_flag = []

    # Build sanitized metrics command; keep known optional flags if present
    sanitized = [parts[0], "metrics"]
    if input_token:
        sanitized.append(input_token)
    else:
        # Fallback: preserve existing tokens to avoid over-stripping
        sanitized.extend(rest)

    if lib_is_valid and existing_lib_flag:
        # Preserve the user's specified library pair
        sanitized.extend(existing_lib_flag)
    elif "--lib" not in rest and "--lib" not in sanitized:
        # Inject default library when missing
        sanitized.extend(["--lib", default_lib])

    # Preserve optional known flags from original command
    for i, tok in enumerate(rest):
        if tok in ("--abc-path", "--opt-script") and i + 1 < len(rest):
            if tok not in sanitized:
                sanitized.extend([tok, rest[i + 1]])
        if tok == "--batch" and "--batch" not in sanitized:
            sanitized.append("--batch")

    return sanitized


def _looks_like_tool_failure(text: str) -> bool:
    low = (text or "").lower()
    failure_markers = [
        "error",
        "failed",
        "traceback",
        "command not found",
        "invalid argument",
        "no such file",
        "unsupported",
        "usage:",
    ]
    return any(m in low for m in failure_markers)


def _parse_tool_status(tool_output: str, command: str = "") -> tuple[bool, int]:
    """
    Parse execute_cktclaw_command return wrapper: [exit=N]
    and infer success/failure.
    """
    out = tool_output or ""
    cmd = (command or "").strip()
    # Internal slash commands (e.g. /reverse): use semantic success markers instead of return_code.
    if cmd.startswith("/"):
        low = out.lower()
        if ("success" in low) or ("module " in low) or (".v" in low):
            return True, 0
    m = re.search(r"\[exit=(-?\d+)\]", out)
    if m:
        code = int(m.group(1))
        return code == 0, code
    # Fallback heuristic when wrapper missing
    return (not _looks_like_tool_failure(out)), (0 if not _looks_like_tool_failure(out) else 1)


def _run_reverse_silent(aig_path: str, cli_state, process_reverse_fn) -> str:
    """
    Execute /reverse pipeline with a temporary in-memory console so that
    tool-calling flow can return a plain text report instead of double-rendering.
    """
    old_console = cli_state.console
    old_verilog = getattr(cli_state, "last_verilog_code", None)
    buf = io.StringIO()
    silent_console = Console(file=buf, force_terminal=False, width=120)
    try:
        cli_state.console = silent_console
        asyncio.run(process_reverse_fn(aig_path, cli_state))
    finally:
        cli_state.console = old_console
    captured = (buf.getvalue() or "").strip()
    return captured


def _build_reverse_tool_result(aig_path: str, cli_state, old_verilog: Optional[str], captured: str) -> str:
    """
    Build a minimal deterministic tool-result payload for /reverse.
    Avoid returning rich boxes/ANSI-heavy long logs to LLM.
    """
    # Hard-link path policy: compute absolute .v path directly from input aig path.
    verilog_path = Path(os.path.abspath(str(aig_path).replace(".aig", ".v")))

    # 1) Prefer on-disk .v if present
    if verilog_path.exists():
        try:
            verilog_code = verilog_path.read_text(encoding="utf-8", errors="ignore")
            # terminal-side debug: verify backend actually read code
            print(f"DEBUG: Read code length: {len(verilog_code)}")
            verilog_code = _truncate_text(verilog_code, 12000)
            return (
                "EXECUTION_STATUS: SUCCESS\n"
                f"VERILOG_PATH_LOCATION: {verilog_path}\n\n"
                "--- START_OF_VERILOG_SOURCE ---\n"
                f"{verilog_code}\n"
                "--- END_OF_VERILOG_SOURCE ---"
            )
        except Exception as e:
            return f"ERROR: Logic executed but file read failed: {e}"

    # 2) Fallback to in-memory generated code
    new_verilog = getattr(cli_state, "last_verilog_code", None)
    if isinstance(new_verilog, str) and new_verilog.strip() and new_verilog != old_verilog:
        print(f"DEBUG: Read code length: {len(new_verilog)}")
        verilog_code = _truncate_text(new_verilog, 12000)
        return (
            "EXECUTION_STATUS: SUCCESS\n"
            "VERILOG_PATH_LOCATION: <in-memory>\n\n"
            "--- START_OF_VERILOG_SOURCE ---\n"
            f"{verilog_code}\n"
            "--- END_OF_VERILOG_SOURCE ---"
        )

    # 3) Final fallback: sanitize captured text
    cleaned = _sanitize_plain_text(captured)
    cleaned = _truncate_text(cleaned, 3000)
    return (
        "ERROR: Reverse pipeline did not produce readable Verilog output.\n"
        "Raw summary:\n"
        f"{cleaned or '(no output)'}"
    )


def _sanitize_plain_text(text: str) -> str:
    """Remove ANSI escapes and rich box-drawing characters."""
    if not text:
        return ""
    # strip ANSI
    text = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)
    # remove common box drawing glyphs
    text = re.sub(r"[┌┐└┘├┤┬┴┼│─╭╮╰╯━┃┏┓┗┛┣┫┳┻╋]+", " ", text)
    # normalize spaces/newlines
    lines = [" ".join(ln.split()) for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln]).strip()


def _truncate_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...[truncated]..."


def _clean_verilog_line_numbers(verilog_raw: str) -> str:
    """
    Strip leading line numbers like '  1 ' / '12 ' from each line.
    """
    if not verilog_raw:
        return ""
    clean_lines = []
    for line in verilog_raw.splitlines():
        cleaned = re.sub(r"^\s*\d+\s*", "", line)
        clean_lines.append(cleaned)
    return "\n".join(clean_lines)


def _compact_tool_output(text: str, max_lines: int = 12) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return "(无输出)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines]) + "\n..."


def _analyze_with_context(
    llm_analyzer,
    messages: list,
    engine: str,
) -> str:
    """
    Fallback method to analyze circuit with context.
    Constructs markdown response from messages.

    Args:
        llm_analyzer: LLMVerilogAnalyzer instance
        messages: Full context messages
        engine: Engine choice

    Returns:
        Analysis response text
    """
    # Extract content from messages for analysis
    # This is a simplified fallback
    verilog_block = None
    user_query = None

    for msg in reversed(messages):
        if msg["role"] == "user" and user_query is None:
            user_query = msg["content"]
        elif msg["role"] == "assistant" and "```verilog" in msg["content"]:
            verilog_block = msg["content"]
            break

    if verilog_block and "```verilog" in verilog_block:
        # Extract Verilog code
        start = verilog_block.find("```verilog")
        end = verilog_block.find("```", start + 10)
        if start >= 0 and end > start:
            verilog_code = verilog_block[start + 10:end].strip()
            # Call analyze on extracted code
            result = llm_analyzer.analyze(verilog_code, engine)
            return result.get("description", "Unable to analyze circuit")

    return "Unable to analyze circuit with provided context"
