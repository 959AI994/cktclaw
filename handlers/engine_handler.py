"""
Engine Handler - /engine command

Handles engine switching between DeepSeek API and local CodeV.
Validates availability and updates session configuration.
"""

from ..config import AVAILABLE_ENGINES, DEFAULT_ENGINE
from ..ui import (
    render_error,
    render_success,
    render_session_info,
    Icons,
)


def switch_engine(engine_choice: str, cli_state) -> None:
    """
    Switch between analysis engines.

    Args:
        engine_choice: "logicrt" or "deepseek"
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    if not engine_choice.strip():
        render_error(
            console,
            f"用法: /engine <{' | '.join(AVAILABLE_ENGINES)}>",
            error_type="error",
        )
        return

    engine_choice = engine_choice.strip().lower()

    # Validate engine choice
    if engine_choice not in AVAILABLE_ENGINES:
        render_error(
            console,
            f"无效的引擎: {engine_choice}。可用: {', '.join(AVAILABLE_ENGINES)}",
            error_type="error",
        )
        return

    # Update state
    old_engine = cli_state.current_engine
    cli_state.current_engine = engine_choice

    # Update session in database
    try:
        # Use cktmem storage instead of old memory_manager
        import asyncio
        asyncio.run(cli_state.storage.update_session(
            cli_state.session_id,
            model_choice=engine_choice
        ))
    except Exception as e:
        render_error(
            console,
            f"会话更新失败: {e}",
            error_type="error",
        )
        return

    # Success message
    console.print()
    render_success(
        console,
        f"引擎已切换: {old_engine} → {engine_choice}",
        title="引擎更新",
    )
    console.print()

    # Display engine info
    engine_details = {
        "当前引擎 Current Engine": engine_choice.upper(),
        "前一个引擎 Previous Engine": old_engine.upper(),
        "会话 Session": cli_state.session_id[:8],
    }

    if engine_choice == "deepseek":
        engine_details["API"] = "ByteDance Volcano Engine (字节跳动火山引擎)"
        engine_details["模型 Model"] = "DeepSeek V3"
        engine_details["类型 Type"] = "云端 Cloud"
    else:  # logicrt
        engine_details["类型 Type"] = "本地推理 Local"
        engine_details["模型 Model"] = "LogicRT (CodeV 融合)"
        engine_details["设备 Device"] = "GPU"

    render_session_info(console, engine_details)
