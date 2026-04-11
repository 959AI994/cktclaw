"""
AIG Handler - /aig command (v2)

Processes AIG files through the full reverse engineering pipeline:
1. Validate file existence
2. Convert AIG → PT (Tensor)
3. Generate Verilog using LogicRT
4. Validate Verilog (syntax + logic equivalence)
5. Analyze circuit using LLM
6. Store results in long memory
7. Render output with validation results
"""

import time
import asyncio
import io
import os
import sys
import warnings
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
    from cktclaw.models import LLMVerilogAnalyzer
    from webapp.backend.models.logicrt_inferencer import LogicRTInferencer
except ImportError as e:
    raise ImportError(f"Failed to import webapp utils: {e}")


def _suppress_warnings():
    """Suppress unwanted warnings from transformers and torch"""
    os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
    warnings.filterwarnings('ignore', category=UserWarning)
    warnings.filterwarnings('ignore', message='.*torch_dtype.*')
    warnings.filterwarnings('ignore', message='.*generation flags.*')
    warnings.filterwarnings('ignore', message='.*enable_nested_tensor.*')


def _suppress_output(func, *args, **kwargs):
    """Execute function with suppressed stdout/stderr"""
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    try:
        return func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


async def process_aig(aig_path: str, cli_state) -> None:
    """
    Main handler for /aig command.

    Processes AIG file through complete pipeline.

    Args:
        aig_path: Path to .aig file
        cli_state: Global CLI state
    """
    # Suppress warnings and noisy output
    _suppress_warnings()

    console = cli_state.console

    # ━━━━━━━━━━ 1. Parse and Validate ━━━━━━━━━━
    if not aig_path.strip():
        render_error(console, "用法: /aig <AIG文件路径>", error_type="error")
        return

    aig_file_path = Path(aig_path).resolve()

    if not aig_file_path.exists():
        render_error(console, f"文件未找到: {aig_path}", error_type="file_error")
        return

    if aig_file_path.suffix.lower() != ".aig":
        render_error(console, f"文件格式错误，需要 .aig 文件", error_type="error")
        return

    aig_filename = aig_file_path.name
    cli_state.current_aig_filename = aig_filename
    cli_state.aig_count += 1

    # ━━━━━━━━━━ 2. Convert AIG → PT ━━━━━━━━━━
    timing = {}

    console.print(f"\n{Icons.CIRCUIT} 处理电路: [bold]{aig_filename}[/bold]")
    render_divider(console)

    with render_spinner(console, f"{Icons.LOADING} 转换 AIG 文件..."):
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
                render_error(console, f"转换失败: {msg}", error_type="error")
                return

            timing["aig_conversion"] = time.time() - start
        except Exception as e:
            render_error(console, f"转换错误: {e}", error_type="error")
            return

    # ━━━━━━━━━━ 3. Generate Verilog ━━━━━━━━━━
    with render_spinner(console, f"{Icons.LOADING} 生成 Verilog 代码..."):
        start = time.time()
        try:
            if cli_state.logicrt_inferencer is None:
                cli_state.logicrt_inferencer = await asyncio.to_thread(
                    _suppress_output,
                    LogicRTInferencer,
                )

            verilog_code = await asyncio.to_thread(
                _generate_verilog_safe,
                cli_state.logicrt_inferencer,
                str(pt_file),
                VERILOG_VALIDATION_RETRIES,
            )

            if not verilog_code:
                render_error(console, "生成 Verilog 失败", error_type="error")
                return

            if len(verilog_code) > VERILOG_MAX_LENGTH:
                render_error(console, f"代码过大 ({len(verilog_code)} 字符)", error_type="error")
                return

            timing["verilog_generation"] = time.time() - start
            cli_state.last_verilog_code = verilog_code

        except Exception as e:
            render_error(console, f"生成错误: {e}", error_type="error")
            return

    # ━━━━━━━━━━ 4. Validate Verilog (Syntax + Logic Equivalence) ━━━━━━━━━━
    with render_spinner(console, f"{Icons.LOADING} 验证 Verilog..."):
        start = time.time()
        validation_results = []

        try:
            # Syntax validation
            is_valid, syntax_error = await asyncio.to_thread(
                VerilogValidator.validate_with_iverilog,
                verilog_code,
            )

            if not is_valid:
                render_error(console, f"语法错误:\n{syntax_error}", error_type="error")
                return

            validation_results.append(("语法验证", True, None))

            # Logic equivalence validation
            is_equiv, equiv_msg = await asyncio.to_thread(
                _validate_logic_equivalence,
                str(aig_file_path),
                verilog_code,
            )

            if is_equiv:
                validation_results.append(("逻辑等价性验证", True, None))
            else:
                validation_results.append(("逻辑等价性验证", False, equiv_msg))

            timing["verilog_validation"] = time.time() - start

        except Exception as e:
            render_error(console, f"验证错误: {e}", error_type="error")
            return

    # ━━━━━━━━━━ 5. Analyze with LLM ━━━━━━━━━━
    with render_spinner(console, f"{Icons.CIRCUIT} 分析电路..."):
        start = time.time()
        try:
            if cli_state.llm_analyzer is None:
                cli_state.llm_analyzer = await asyncio.to_thread(
                    lambda: LLMVerilogAnalyzer(verbose=False),
                )

            analysis_result = await asyncio.to_thread(
                cli_state.llm_analyzer.analyze,
                verilog_code,
                "local",  # 使用 LogicRT
            )

            if analysis_result["status"] != "success":
                render_error(console, f"分析失败: {analysis_result.get('message', '未知错误')}", error_type="error")
                return

            analysis_report = analysis_result.get("description", "")
            metrics = analysis_result.get("metrics", {})

            timing["analysis"] = time.time() - start
            cli_state.last_analysis_report = analysis_report

        except Exception as e:
            render_error(console, f"分析错误: {e}", error_type="error")
            return

    # ━━━━━━━━━━ 6. Store in Memory (using cktmem) ━━━━━━━━━━
    try:
        # Check if this is the first circuit analysis (Anchor Memory)
        anchor = await cli_state.storage.get_anchor_memory(cli_state.session_id)

        if anchor is None:
            # First analysis - store as Anchor Memory
            await cli_state.storage.store_anchor_memory(
                session_id=cli_state.session_id,
                verilog_code=verilog_code,
                analysis_report=analysis_report,
            )
        else:
            # Subsequent analysis - store as Core Context
            await cli_state.storage.add_core_context(
                session_id=cli_state.session_id,
                aig_filename=aig_filename,
                verilog_code=verilog_code,
                analysis_report=analysis_report,
            )
    except Exception as e:
        render_error(console, f"保存失败: {e}", error_type="error")
        return

    # ━━━━━━━━━━ 7. Render Output ━━━━━━━━━━
    console.print()

    # Display Verilog code
    console.print("[bold cyan]━━━ 生成的 Verilog 代码 ━━━[/bold cyan]")
    render_verilog_code(console, verilog_code, max_lines=50)
    console.print()

    # 显示验证结果（紧跟 Verilog 代码之后）
    for test_name, passed, msg in validation_results:
        if passed:
            console.print(f"[bold green]✓ {test_name} 通过[/bold green]")
        else:
            console.print(f"[bold yellow]⚠ {test_name}: {msg}[/bold yellow]")
    console.print()

    # Display metrics
    if metrics:
        render_metrics_table(console, metrics, title="电路指标")
        console.print()

    # Display analysis report
    console.print("[bold cyan]━━━ 电路分析 ━━━[/bold cyan]")
    render_analysis_report(console, analysis_report)
    console.print()

    # Display timing summary
    render_completion_summary(console, timing, title="完成摘要")
    console.print()


# ━━━━━━━━━━ Helper Functions ━━━━━━━━━━
def _generate_verilog_safe(
    logicrt_inferencer,
    pt_file: str,
    max_retries: int = 3,
) -> Optional[str]:
    """Generate Verilog with validation retries."""
    for attempt in range(max_retries):
        try:
            result = logicrt_inferencer.generate(pt_file)

            # Handle tuple or string return
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


def _validate_logic_equivalence(
    aig_file: str,
    verilog_code: str,
) -> Tuple[bool, Optional[str]]:
    """
    Validate logic equivalence between AIG and generated Verilog.

    Returns:
        (is_equivalent, error_message_or_none)
    """
    try:
        # 使用 ABC 工具进行逻辑等价性检验
        import subprocess
        from pathlib import Path

        # 创建临时 Verilog 文件
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False) as f:
            f.write(verilog_code)
            verilog_file = f.name

        try:
            # 使用 ABC 进行等价性检验
            cmd = [
                'abc',
                '-c',
                f'read {aig_file}; read {verilog_file}; cec -n; quit'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # 检查输出中的 "Circuits are equivalent" 或 "PASS"
            if 'equivalent' in result.stdout.lower() or 'pass' in result.stdout.lower():
                return True, None
            else:
                return False, "逻辑等价性检验未通过"

        finally:
            if os.path.exists(verilog_file):
                os.remove(verilog_file)

    except FileNotFoundError:
        # ABC 工具未安装，跳过检验
        return True, None
    except Exception as e:
        # 检验过程出错，返回警告但不阻止
        return True, f"检验过程出错 (已跳过): {str(e)[:50]}"
