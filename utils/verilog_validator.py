"""
Verilog 语法验证工具
使用 iverilog 或 pyverilog 进行语法检查
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Tuple, Optional


class VerilogValidator:
    """Verilog 代码语法验证"""

    @staticmethod
    def validate_with_iverilog(verilog_code: str) -> Tuple[bool, Optional[str]]:
        """
        使用 iverilog 验证 Verilog 语法

        Args:
            verilog_code: Verilog 源代码

        Returns:
            (is_valid: bool, error_message: Optional[str])
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False) as f:
                f.write(verilog_code)
                temp_file = f.name

            try:
                # 运行 iverilog 进行语法检查
                result = subprocess.run(
                    ['iverilog', '-tnull', temp_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    return True, None
                else:
                    error = result.stderr if result.stderr else result.stdout
                    return False, error

            finally:
                # 清理临时文件
                if os.path.exists(temp_file):
                    os.remove(temp_file)

        except FileNotFoundError:
            return False, "iverilog not found. Please install Icarus Verilog."
        except subprocess.TimeoutExpired:
            return False, "iverilog validation timeout"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def validate_with_pyverilog(verilog_code: str) -> Tuple[bool, Optional[str]]:
        """
        使用 pyverilog 验证 Verilog 语法

        Args:
            verilog_code: Verilog 源代码

        Returns:
            (is_valid: bool, error_message: Optional[str])
        """
        try:
            from pyverilog.verilog_parser import parse
            from pyverilog.ast_code_generator import ASTCodeGenerator

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False) as f:
                f.write(verilog_code)
                temp_file = f.name

            try:
                # 尝试解析
                ast, directives = parse([temp_file])
                return True, None

            except Exception as e:
                return False, str(e)

            finally:
                # 清理临时文件
                if os.path.exists(temp_file):
                    os.remove(temp_file)

        except ImportError:
            return False, "pyverilog not available"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def validate(verilog_code: str, prefer_method: str = "iverilog") -> Tuple[bool, Optional[str]]:
        """
        验证 Verilog 代码语法

        Args:
            verilog_code: Verilog 源代码
            prefer_method: 优先使用的验证方法 ("iverilog" 或 "pyverilog")

        Returns:
            (is_valid: bool, error_message: Optional[str])
        """
        if prefer_method == "iverilog":
            is_valid, error = VerilogValidator.validate_with_iverilog(verilog_code)
            if error and "not found" in error:
                # 如果 iverilog 不可用，尝试 pyverilog
                return VerilogValidator.validate_with_pyverilog(verilog_code)
            return is_valid, error
        else:
            is_valid, error = VerilogValidator.validate_with_pyverilog(verilog_code)
            if error and "not available" in error:
                # 如果 pyverilog 不可用，尝试 iverilog
                return VerilogValidator.validate_with_iverilog(verilog_code)
            return is_valid, error

    @staticmethod
    def clean_code(verilog_code: str) -> str:
        """
        清理 Verilog 代码（移除多余的换行、空格等）

        Args:
            verilog_code: 原始 Verilog 代码

        Returns:
            清理后的代码
        """
        import re

        # 移除多余的空行（多于 2 个连续换行）
        code = re.sub(r'\n{3,}', '\n\n', verilog_code)

        # 移除行末尾的空格
        code = '\n'.join(line.rstrip() for line in code.split('\n'))

        return code.strip()
