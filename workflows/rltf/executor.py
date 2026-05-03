"""
RLTF Executor - ABC/OpenSTA 执行器

负责执行 ABC 优化和 OpenSTA 时序分析，提取 PPA 指标。
"""

import re
import os
import time
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# 使用相对导入避免循环依赖
import sys
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from eda_tools import ABCRunner, OpenSTARunner
from .types import PPAMetrics


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    output: str
    output_file: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None


class RLTFExecutor:
    """
    RLTF 执行器

    封装 ABC 和 OpenSTA 工具的调用，提取 PPA 指标。
    """

    def __init__(self):
        """初始化执行器"""
        self.abc_runner = ABCRunner()
        self.opensta_runner = OpenSTARunner()

    async def get_initial_metrics(self, aig_file_path: str) -> PPAMetrics:
        """
        获取初始 PPA 指标

        Args:
            aig_file_path: AIG 文件路径

        Returns:
            初始 PPA 指标
        """
        # 使用 ABC 的 ps (print_stats) 命令获取统计信息
        result = await self.execute_abc(
            aig_file_path,
            "ps",
            timeout=30,
            read_only=True
        )

        if not result.success:
            raise RuntimeError(f"Failed to get initial metrics: {result.error}")

        metrics = self._parse_abc_stats(result.output)
        if not metrics.metrics_valid:
            raise RuntimeError(
                "Failed to parse initial ABC stats (no and/lev line in ps output)"
            )
        return metrics

    async def execute_abc(
        self,
        input_file: str,
        sequence: str,
        timeout: int = 30,
        read_only: bool = False,
    ) -> ExecutionResult:
        """
        执行 ABC 优化

        Args:
            input_file: 输入 AIG 文件
            sequence: ABC 命令序列
            timeout: 超时时间（秒）
            read_only: 是否只读模式（不生成输出文件）

        Returns:
            执行结果
        """
        start_time = time.time()

        try:
            # 生成输出文件路径
            output_file = None
            if not read_only:
                output_file = self._generate_temp_file(".aig")

            # 构建 ABC 命令
            commands = [
                f"read_aiger {input_file}",
            ]

            # 添加优化序列。dch 会产生 choice network，后续 rw/rwz 等需纯 AIG；
            # 在每条 dch 后自动插入 strash，避免 "choice nodes" 类错误。
            for cmd in sequence.split(';'):
                cmd = cmd.strip()
                if not cmd:
                    continue
                commands.append(cmd)
                first_tok = cmd.split()[0] if cmd.split() else ""
                if first_tok == "dch":
                    commands.append("strash")

            # 添加统计和输出命令
            commands.append("ps")
            if output_file:
                commands.append(f"write_aiger {output_file}")

            # 只传 ABC 内联脚本；由 ABCRunner 负责加「-c」和可执行文件路径。
            abc_script = "; ".join(commands)
            result = self.abc_runner.run(abc_script, timeout=timeout)

            duration = time.time() - start_time

            combined_out = result.stdout or ""
            if result.stderr:
                combined_out = combined_out + "\n" + result.stderr

            if result.error:
                return ExecutionResult(
                    success=False,
                    output=combined_out,
                    duration=duration,
                    error=result.error,
                )

            return ExecutionResult(
                success=True,
                output=combined_out,
                output_file=output_file,
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                duration=duration,
                error=str(e),
            )

    async def execute_opensta(
        self,
        verilog_file: str,
        timeout: int = 60,
    ) -> ExecutionResult:
        """
        执行 OpenSTA 时序分析

        Args:
            verilog_file: Verilog 文件路径
            timeout: 超时时间（秒）

        Returns:
            执行结果
        """
        start_time = time.time()

        try:
            # 生成 STA 脚本
            script_file = self._generate_temp_file(".tcl")
            script_content = f"""
read_verilog {verilog_file}
link_design top
report_checks -path_delay max
report_checks -path_delay min
"""

            # 写入脚本文件
            with open(script_file, 'w') as f:
                f.write(script_content)

            # 执行 OpenSTA
            sta_command = f"sta -script {script_file}"
            result = self.opensta_runner.run(sta_command)

            duration = time.time() - start_time

            # 清理临时文件
            try:
                os.remove(script_file)
            except:
                pass

            # 检查执行结果
            if result.error:
                return ExecutionResult(
                    success=False,
                    output=result.stdout or "",
                    duration=duration,
                    error=result.error,
                )

            return ExecutionResult(
                success=True,
                output=result.stdout or "",
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            return ExecutionResult(
                success=False,
                output="",
                duration=duration,
                error=str(e),
            )

    async def extract_metrics(
        self,
        abc_result: ExecutionResult,
        sta_result: Optional[ExecutionResult] = None,
    ) -> PPAMetrics:
        """
        从执行结果中提取 PPA 指标

        Args:
            abc_result: ABC 执行结果
            sta_result: OpenSTA 执行结果（可选）

        Returns:
            PPA 指标
        """
        # 从 ABC 输出中提取 area 和基本信息
        metrics = self._parse_abc_stats(abc_result.output)

        # 若有 STA 结果且 ABC 统计已可靠解析，再用 STA 覆盖 delay
        if (
            sta_result
            and sta_result.success
            and metrics.metrics_valid
        ):
            delay = self._parse_sta_delay(sta_result.output)
            if delay is not None:
                metrics.delay = delay

        return metrics

    def _parse_abc_stats(self, output: str) -> PPAMetrics:
        """
        解析 ABC 统计输出

        ABC ps 命令输出格式示例：
        test                 : i/o =    8/    1  lat =    0  and =   104   lev =    7

        Args:
            output: ABC 输出

        Returns:
            PPA 指标
        """
        # 默认值
        area = 0
        delay = 0.0
        node_count = 0
        edge_count = 0
        levels = 0
        stats_found = False

        # 查找统计信息行
        for line in output.split('\n'):
            line = line.strip()

            # 匹配 ABC ps 输出格式
            # 格式: name : i/o = X/ Y lat = Z and = N lev = L
            match = re.search(
                r'and\s*=\s*(\d+)\s+lev\s*=\s*(\d+)',
                line
            )

            if match:
                and_count = int(match.group(1))
                levels = int(match.group(2))

                area = and_count

                delay = levels * 0.1
                stats_found = True
                break

        return PPAMetrics(
            area=area,
            delay=delay,
            node_count=node_count,
            edge_count=edge_count,
            levels=levels,
            metrics_valid=stats_found,
        )

    def _parse_sta_delay(self, output: str) -> Optional[float]:
        """
        解析 OpenSTA 延迟输出

        Args:
            output: OpenSTA 输出

        Returns:
            延迟值（ns），如果解析失败返回 None
        """
        # 查找延迟信息
        # OpenSTA 输出格式示例：
        # Startpoint: in1 (input port)
        # Endpoint: out1 (output port)
        # Path Delay: 2.45

        for line in output.split('\n'):
            line = line.strip()

            # 匹配延迟行
            match = re.search(r'(?:Path\s+)?Delay[:\s]+(\d+\.?\d*)', line, re.IGNORECASE)
            if match:
                return float(match.group(1))

            # 匹配 slack 行（如果有）
            match = re.search(r'slack[:\s]+(-?\d+\.?\d*)', line, re.IGNORECASE)
            if match:
                # 如果只有 slack，无法直接得到 delay
                # 这里返回 None，使用 ABC 的估计值
                pass

        return None

    def _generate_temp_file(self, suffix: str) -> str:
        """
        生成临时文件路径

        Args:
            suffix: 文件后缀

        Returns:
            临时文件路径
        """
        temp_dir = tempfile.gettempdir()
        temp_file = tempfile.NamedTemporaryFile(
            suffix=suffix,
            dir=temp_dir,
            delete=False
        )
        temp_path = temp_file.name
        temp_file.close()
        return temp_path

    def cleanup_temp_files(self, file_paths: list[str]) -> None:
        """
        清理临时文件

        Args:
            file_paths: 文件路径列表
        """
        for file_path in file_paths:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                # 忽略清理错误
                pass
