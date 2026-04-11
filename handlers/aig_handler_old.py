"""
AIG Handler - /aig command

Processes AIG files through the full reverse engineering pipeline:
1. Validate file existence
2. Convert AIG → PT (Tensor)
3. Generate Verilog using LogicRT
4. Validate Verilog syntax
5. Analyze circuit using LLM (DeepSeek or Local CodeV)
6. Store results in long memory
7. Render output with spinners/progress and syntax highlighting
"""

import time
import asyncio
from pathlib import Path
from typing import Optional, Tuple

from ..config import (
    INFERENCE_TIMEOUT,
    VERILOG_VALIDATION_RETRIES,
    VERILOG_MAX_LENGTH,
    AIG_TO_PT_TIMEOUT,
)
from ..ui import (
    render_error,
    render_success,
    render_verilog_code,
    render_analysis_report,
    render_metrics_table,
    render_completion_summary,
    render_spinner,
    render_divider,
    Icons,
    format_time,
)

# Import webapp utilities
try:
    from webapp.backend.utils.aig_converter import convert_aig_to_pt
    from webapp.backend.utils.verilog_validator import VerilogValidator
    from webapp.backend.models.llm_analyzer import LLMVerilogAnalyzer
    from webapp.backend.models.logicrt_inferencer import LogicRTInferencer
except ImportError as e:
    raise ImportError(f"Failed to import webapp utils: {e}")


async def process_aig(aig_path: str, cli_state) -> None:
    """
    Main handler for /aig command.

    Processes AIG file through complete pipeline:
    1. Parse and validate file path
    2. Create/update session with AIG filename
    3. Convert AIG to Tensor format
    4. Generate Verilog using LogicRT
    5. Validate Verilog syntax
    6. Analyze with LLM
    7. Store in long memory
    8. Render output

    Args:
        aig_path: Path to .aig file (from command args)
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    # ━━━━━━━━━━ 1. Parse and Validate ━━━━━━━━━━
    if not aig_path.strip():
        render_error(console, "Usage: /aig <path_to_file.aig>", error_type="error")
        return

    aig_file_path = Path(aig_path).resolve()

    if not aig_file_path.exists():
        render_error(
            console,
            f"File not found: {aig_path}",
            error_type="file_error",
        )
        return

    if aig_file_path.suffix.lower() != ".aig":
        render_error(
            console,
            f"File must be .aig format, got: {aig_file_path.suffix}",
            error_type="error",
        )
        return

    # Update session with AIG filename
    aig_filename = aig_file_path.name
    cli_state.current_aig_filename = aig_filename
    cli_state.aig_count += 1

    # ━━━━━━━━━━ 2. Convert AIG → PT ━━━━━━━━━━
    timing = {}

    console.print(f"\n{Icons.CIRCUIT} Processing: [bold]{aig_filename}[/bold]")
    render_divider(console)

    with render_spinner(console, f"{Icons.LOADING} Converting AIG to Tensor format..."):
        start = time.time()
        try:
            pt_file = aig_file_path.with_suffix(".pt")
            success, msg = await asyncio.to_thread(
                convert_aig_to_pt,
                str(aig_file_path),
                str(pt_file),
                None,
                AIG_TO_PT_TIMEOUT,
            )

            if not success:
                render_error(
                    console,
                    f"AIG conversion failed: {msg}",
                    error_type="error",
                )
                return

            timing["aig_conversion"] = time.time() - start
        except Exception as e:
            render_error(
                console,
                f"AIG conversion error: {e}",
                error_type="error",
            )
            return

    # ━━━━━━━━━━ 3. Generate Verilog ━━━━━━━━━━
    with render_spinner(console, f"{Icons.LOADING} 正在生成 Verilog 代码..."):
        start = time.time()
        try:
            # Lazy-load LogicRT inferencer
            if cli_state.logicrt_inferencer is None:
                # 重定向模型加载日志（用户不需要看到详细过程）
                import sys
                import io

                # 保存原始 stdout/stderr
                old_stdout = sys.stdout
                old_stderr = sys.stderr

                # 重定向到字符串缓冲区
                sys.stdout = io.StringIO()
                sys.stderr = io.StringIO()

                try:
                    cli_state.logicrt_inferencer = LogicRTInferencer()
                finally:
                    # 恢复 stdout/stderr
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

            # Generate Verilog
            verilog_code = await asyncio.to_thread(
                _generate_verilog_safe,
                cli_state.logicrt_inferencer,
                str(pt_file),
                VERILOG_VALIDATION_RETRIES,
            )

            if not verilog_code:
                render_error(
                    console,
                    "Verilog 生成失败：输出为空",
                    error_type="error",
                )
                return

            if len(verilog_code) > VERILOG_MAX_LENGTH:
                render_error(
                    console,
                    f"生成的 Verilog 代码过大 ({len(verilog_code)} 字符)",
                    error_type="error",
                )
                return

            timing["verilog_generation"] = time.time() - start
            cli_state.last_verilog_code = verilog_code

        except Exception as e:
            render_error(
                console,
                f"Verilog 生成错误: {e}",
                error_type="error",
            )
            return

    # ━━━━━━━━━━ 4. Validate Verilog ━━━━━━━━━━
    with render_spinner(console, f"{Icons.LOADING} Validating Verilog syntax..."):
        start = time.time()
        try:
            is_valid, error_msg = await asyncio.to_thread(
                VerilogValidator.validate_with_iverilog,
                verilog_code,
            )

            if not is_valid:
                render_error(
                    console,
                    f"Verilog syntax error:\n{error_msg}",
                    error_type="error",
                )
                return

            timing["verilog_validation"] = time.time() - start

        except Exception as e:
            render_error(
                console,
                f"Validation error: {e}",
                error_type="error",
            )
            return

    # ━━━━━━━━━━ 5. Analyze with LLM ━━━━━━━━━━
    with render_spinner(console, f"{Icons.CIRCUIT} Analyzing circuit with {cli_state.current_engine}..."):
        start = time.time()
        try:
            # Lazy-load LLM analyzer
            if cli_state.llm_analyzer is None:
                cli_state.llm_analyzer = LLMVerilogAnalyzer()

            # Analyze
            analysis_result = await asyncio.to_thread(
                cli_state.llm_analyzer.analyze,
                verilog_code,
                cli_state.current_engine,
            )

            if analysis_result["status"] != "success":
                render_error(
                    console,
                    f"Analysis failed: {analysis_result.get('message', 'Unknown error')}",
                    error_type="error",
                )
                return

            analysis_report = analysis_result.get("description", "")
            metrics = analysis_result.get("metrics", {})

            timing["analysis"] = time.time() - start
            cli_state.last_analysis_report = analysis_report

        except Exception as e:
            render_error(
                console,
                f"Analysis error: {e}",
                error_type="error",
            )
            return

    # ━━━━━━━━━━ 6. Store in Long Memory ━━━━━━━━━━
    try:
        cli_state.memory_manager.store_long_memory(
            cli_state.session_id,
            verilog_code,
            analysis_report,
        )
    except Exception as e:
        render_error(
            console,
            f"Failed to store in memory: {e}",
            error_type="error",
        )
        return

    # ━━━━━━━━━━ 7. Render Output ━━━━━━━━━━
    console.print()
    render_divider(console)
    console.print()

    # Display Verilog code (with syntax highlighting)
    console.print("[bold cyan]━━━ Generated Verilog Code ━━━[/bold cyan]")
    render_verilog_code(console, verilog_code, max_lines=50)
    console.print()

    # Display metrics table
    if metrics:
        render_metrics_table(console, metrics)
        console.print()

    # Display analysis report
    console.print("[bold cyan]━━━ Circuit Analysis ━━━[/bold cyan]")
    render_analysis_report(console, analysis_report)
    console.print()

    # Display timing summary
    render_completion_summary(console, timing)
    console.print()


# ━━━━━━━━━━ Helper Functions ━━━━━━━━━━
def _generate_verilog_safe(
    logicrt_inferencer,
    pt_file: str,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Generate Verilog with validation retries.

    Args:
        logicrt_inferencer: LogicRTInferencer instance
        pt_file: Path to .pt file
        max_retries: Number of retry attempts

    Returns:
        Generated Verilog code, or None if failed
    """
    for attempt in range(max_retries):
        try:
            # LogicRTInferencer.generate() 返回 (verilog_code, info_dict)
            result = logicrt_inferencer.generate(pt_file)

            # 处理返回值（可能是 tuple 或 string）
            if isinstance(result, tuple):
                verilog_code = result[0]
            else:
                verilog_code = result

            if verilog_code and len(verilog_code.strip()) > 0:
                return verilog_code

        except Exception as e:
            if attempt < max_retries - 1:
                continue
            raise

    return None
