"""
AIG to PT 文件转换工具
调用 AI4EDA-OpenABC-Data-Toolkit 进行转换
"""

import subprocess
import os
from pathlib import Path
from typing import Tuple, Optional

from config import AI4EDA_TOOLKIT_PATH

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

    优先使用 Python API，失败时回退到命令行方式

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

    # 优先尝试 Python API 方式（避免相对导入问题）
    try:
        return convert_aig_to_pt_python_api(aig_file, pt_file, abc_path)
    except Exception as api_error:
        # 回退到命令行方式（使用 -m 参数）
        try:
            # 使用 python -m 来避免相对导入问题
            cmd = [
                "python",
                "-m",
                "ai4eda.converters.aig_to_pt",
                str(aig_file),
                str(pt_file),
            ]

            # 添加 ABC 路径（如果指定）
            if abc_path:
                cmd.extend(["--abc-path", abc_path])
            else:
                # 尝试从环境变量获取
                env_abc = os.environ.get("ABC_PATH")
                if env_abc:
                    cmd.extend(["--abc-path", env_abc])

            # 执行转换
            result = subprocess.run(
                cmd,
                cwd=str(TOOLKIT_PATH),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                if Path(pt_file).exists():
                    return True, f"Converted: {aig_file} -> {pt_file}"
                else:
                    return False, f"Output file not created: {pt_file}"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                return False, f"Conversion failed: {error_msg}"

        except subprocess.TimeoutExpired:
            return False, f"Conversion timeout after {timeout}s"
        except Exception as e:
            return False, f"Both API and CLI conversion failed. API error: {api_error}, CLI error: {str(e)}"


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

        converter = AigToPTConverter(abc_path=abc_path or os.environ.get("ABC_PATH"))
        success, message = converter.convert(aig_file, pt_file)

        return success, message

    except ImportError as e:
        return False, f"Failed to import AI4EDA toolkit: {str(e)}"
    except Exception as e:
        return False, f"Conversion error: {str(e)}"
