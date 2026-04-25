"""
AIG to PT 文件转换工具
调用 AI4EDA-OpenABC-Data-Toolkit 进行转换
"""

import subprocess
import os
from pathlib import Path
from typing import Tuple, Optional

from config import AI4EDA_TOOLKIT_PATH, ABC_PATH as CONFIG_ABC_PATH

# AI4EDA Toolkit 路径（优先使用 CKTCLAW_AI4EDA_PATH 环境变量，其次 config.py 默认值）
TOOLKIT_PATH = Path(AI4EDA_TOOLKIT_PATH)


def convert_aig_to_pt(
    aig_file: str,
    pt_file: str,
    abc_path: Optional[str] = None,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """
    将 AIG 文件转换为 PyTorch Tensor (.pt) 格式

    优先使用命令行子进程方式（隔离 torch/CUDA 初始化），失败时回退到 Python API

    Args:
        aig_file: 输入 .aig 文件路径
        pt_file: 输出 .pt 文件路径
        abc_path: ABC 工具路径（可选，默认从环境变量或系统 PATH 获取）
        timeout: 转换超时时间（秒）

    Returns:
        (success: bool, message: str)
    """
    if not TOOLKIT_PATH.exists():
        return False, f"AI4EDA Toolkit not found at {TOOLKIT_PATH}"

    if not Path(aig_file).exists():
        return False, f"AIG file not found: {aig_file}"

    # Python API 优先：in-process 调用 AigToPTConverter，已验证可用。
    # （subprocess 路径假设 ai4eda.converters.aig_to_pt 有 __main__ 入口，
    # 但当前 vendored 副本是纯库模块，python -m 会立即退出且不产出文件，
    # 这是 "Output file not created" 报错的根因）
    api_msg = ""
    try:
        api_success, api_msg = convert_aig_to_pt_python_api(aig_file, pt_file, abc_path)
        if api_success:
            return True, api_msg
    except Exception as api_error:
        api_msg = f"API exception: {api_error}"

    # CLI 兜底：留给未来 ai4eda 提供 CLI 入口时使用
    try:
        cli_success, cli_msg = convert_aig_to_pt_cli(aig_file, pt_file, abc_path, timeout)
        if cli_success:
            return True, cli_msg
        return False, f"API failed ({api_msg}); CLI failed ({cli_msg})"
    except Exception as cli_error:
        return False, f"API failed ({api_msg}); CLI exception: {cli_error}"


def convert_aig_to_pt_cli(
    aig_file: str,
    pt_file: str,
    abc_path: Optional[str] = None,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """
    使用命令行子进程调用 AI4EDA（推荐）
    """
    # 使用 python -m 来避免相对导入问题
    cmd = [
        "python",
        "-m",
        "ai4eda.converters.aig_to_pt",
        str(aig_file),
        str(pt_file),
    ]

    # 添加 ABC 路径：参数 > 环境变量 > config 默认值
    effective_abc_cli = abc_path or os.environ.get("ABC_PATH") or CONFIG_ABC_PATH
    cmd.extend(["--abc-path", effective_abc_cli])

    # 在子进程中固定可见 GPU 到 0..4，避免出现 device=5, num_gpus=5 越界
    child_env = os.environ.copy()
    child_env["CUDA_VISIBLE_DEVICES"] = "0,1,2,3,4"

    result = subprocess.run(
        cmd,
        cwd=str(TOOLKIT_PATH),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=child_env,
    )

    if result.returncode == 0:
        if Path(pt_file).exists():
            return True, f"Converted: {aig_file} -> {pt_file}"
        return False, f"Output file not created: {pt_file}"

    error_msg = result.stderr if result.stderr else result.stdout
    return False, f"Conversion failed: {error_msg}"


def convert_aig_to_pt_python_api(
    aig_file: str,
    pt_file: str,
    abc_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    使用 Python API 直接调用（无需命令行）
    """
    try:
        # 添加 toolkit 到 sys.path
        import sys
        if str(TOOLKIT_PATH) not in sys.path:
            sys.path.insert(0, str(TOOLKIT_PATH))

        from ai4eda.converters.aig_to_pt import AigToPTConverter

        effective_abc = abc_path or os.environ.get("ABC_PATH") or CONFIG_ABC_PATH
        # User-facing hyperparameter:
        #   CKTCLAW_BENCH_FORMAT=gate|lut|auto
        # Default to gate to avoid LUT BENCH breaking downstream graph conversion.
        bench_format = (os.environ.get("CKTCLAW_BENCH_FORMAT", "gate") or "gate").strip().lower()
        converter = AigToPTConverter(abc_path=effective_abc, bench_format=bench_format)
        success, message = converter.convert(aig_file, pt_file)

        return success, message

    except ImportError as e:
        return False, f"Failed to import AI4EDA toolkit: {str(e)}"
    except Exception as e:
        return False, f"Conversion error: {str(e)}"
