"""
Dynamic EDA command dictionaries for interactive builders.

At import time, this module attempts to invoke local tools:
- yosys -p "help"
- abc   -c "help"

It parses the help listings into {command: zh_desc} dictionaries for
use as meta_dict in prompt_toolkit completers.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Dict, Tuple


def _run_cmd(cmd: list[str]) -> Tuple[int, str, str]:
	"""Run a command and capture stdout/stderr as text."""
	try:
		proc = subprocess.run(
			cmd,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			timeout=10,
		)
		return proc.returncode, proc.stdout or "", proc.stderr or ""
	except Exception as e:
		return -1, "", str(e)


def _translate_en_to_zh_short(en: str) -> str:
	"""
	Heuristic, concise CN translation of short English descriptions.
	We keep it compact and safe. If we can't infer, fall back to EN.
	"""
	s = en.strip()
	low = s.lower()
	# Common verb mappings
	mapping = [
		("read", "读取"),
		("write", "写出"),
		("map", "映射"),
		("synth", "综合"),
		("opt", "优化"),
		("clean", "清理"),
		("flatten", "扁平化"),
		("stat", "统计"),
		("select", "选择/查看"),
		("delete", "删除"),
		("copy", "复制"),
		("rename", "重命名"),
		("show", "可视化/示意图"),
		("eval", "求值/仿真"),
		("sim", "仿真"),
		("equiv", "等价性"),
		("fsm", "状态机"),
		("memory", "存储器处理"),
		("techmap", "工艺映射"),
		("proc", "进程转换"),
		("dff", "触发器处理"),
		("mux", "多路复用处理"),
		("share", "资源共享"),
		("verilog", "Verilog 相关"),
		("json", "JSON 相关"),
		("liberty", "Liberty 相关"),
		("abc", "ABC 综合/映射"),
		("aiger", "AIGER 相关"),
	]
	for key, zh in mapping:
		if key in low:
			return f"{zh}：{s}"
	# Fallback: keep EN with CN tag
	return f"说明：{s}"


def _parse_yosys_help(out: str) -> Dict[str, str]:
	"""
	Parse `yosys -p "help"` output: lines like
	    command             short description
	"""
	cmds: Dict[str, str] = {}
	for line in out.splitlines():
		# Match: <name><spaces><desc>
		m = re.match(r"^\s*([a-zA-Z0-9_]+)\s{2,}(.+)$", line)
		if not m:
			continue
		name, desc = m.group(1).strip(), m.group(2).strip()
		# Avoid generic headers
		if name in {"Type", "End", "Yosys"}:
			continue
		cmds[name] = _translate_en_to_zh_short(desc)
	return cmds


def _parse_abc_help(out: str) -> Dict[str, str]:
	"""
	Parse `abc -c "help"` output. ABC prints many lines like:
	    command [args]  : short description
	We'll capture the first token as command name.
	"""
	cmds: Dict[str, str] = {}
	for line in out.splitlines():
		# Example patterns:
		# "read_blif [-s] filename     : reads BLIF file"
		# "fraig                        : fraigs the current network"
		m = re.match(r"^\s*([a-zA-Z0-9_]+)\b.*?:\s*(.+)$", line)
		if not m:
			continue
		name, desc = m.group(1).strip(), m.group(2).strip()
		cmds[name] = _translate_en_to_zh_short(desc)
	return cmds


def build_command_dicts() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], int, int, int]:
	"""
	Build (ABC_COMMANDS, YOSYS_COMMANDS, OPENSTA_COMMANDS, abc_count, yosys_count, opensta_count).
	Runs local tools when available; otherwise returns partial dicts.
	"""
	abc_cmds: Dict[str, str] = {}
	yosys_cmds: Dict[str, str] = {}
	opensta_cmds: Dict[str, str] = {}

	# Yosys
	if shutil.which("yosys"):
		rc, out, _ = _run_cmd(["yosys", "-p", "help"])
		if rc == 0 and out:
			yosys_cmds = _parse_yosys_help(out)

	# ABC
	# Prefer ABC_PATH from env if present
	abc_exe = os.environ.get("ABC_PATH", "abc")
	if shutil.which(abc_exe):
		rc, out, _ = _run_cmd([abc_exe, "-c", "help"])
		if rc == 0 and out:
			abc_cmds = _parse_abc_help(out)

	# OpenSTA
	# Prefer OPENSTA_PATH from env if present
	opensta_exe = os.environ.get("OPENSTA_PATH", "sta")
	if shutil.which(opensta_exe):
		# OpenSTA doesn't have a simple help command, so we provide static commands
		opensta_cmds = {
			"read_liberty": "📥 读取 Liberty 时序库文件 (.lib)",
			"read_verilog": "📥 读取 Verilog 网表文件 (.v)",
			"read_sdc": "📥 读取 SDC 约束文件 (.sdc)",
			"link_design": "🔗 链接设计顶层模块",
			"create_clock": "🕐 创建时钟约束",
			"set_input_delay": "⏱️ 设置输入延迟约束",
			"set_output_delay": "⏱️ 设置输出延迟约束",
			"set_load": "⚡ 设置负载电容",
			"report_checks": "📊 报告时序路径检查",
			"report_worst_slack": "⚠️ 报告最差时序裕量",
			"report_tns": "📉 报告总负时序裕量 (TNS)",
			"report_wns": "📉 报告最差负时序裕量 (WNS)",
			"report_power": "🔋 报告功耗分析",
			"report_clock_skew": "🕐 报告时钟偏斜",
			"write_sdf": "📤 导出 SDF 延迟文件",
			"write_spef": "📤 导出 SPEF 寄生参数文件",
		}

	# Always append system-level helper commands
	abc_cmds["run"] = "🚀 立即执行已拼装的完整命令串"
	abc_cmds["cancel"] = "❌ 清空当前输入并退出构建器"

	yosys_cmds["run"] = "🚀 立即执行已拼装的完整命令串"
	yosys_cmds["cancel"] = "❌ 清空当前输入并退出构建器"

	opensta_cmds["run"] = "🚀 立即执行已拼装的完整命令串"
	opensta_cmds["cancel"] = "❌ 清空当前输入并退出构建器"

	return abc_cmds, yosys_cmds, opensta_cmds, len(abc_cmds), len(yosys_cmds), len(opensta_cmds)


# Build at import time for immediate availability to handlers.
ABC_COMMANDS, YOSYS_COMMANDS, OPENSTA_COMMANDS, ABC_COUNT, YOSYS_COUNT, OPENSTA_COUNT = build_command_dicts()

# ───────────────────── AI4EDA-OpenABC-Data-Toolkit ───────────────────── #
# Dynamically constructed nested command tree based on discovered CLI (ai4eda/cli.py)
AI4EDA_COMMANDS = {
	"convert": {
		"aig2bench": "格式转换: AIG -> BENCH",
		"bench2graphml": "格式转换: BENCH -> GraphML",
		"graphml2pt": "格式转换: GraphML -> PyTorch Geometric (.pt)",
		"verilog2aig": "格式转换: Verilog(.v) -> AIG",
		"aig2pt": "🔥 一键直转: AIG -> PyTorch Geometric (.pt)",
		"verilog2pt": "🔥 一键直转: Verilog(.v) -> PyTorch Geometric (.pt)",
	},
	"metrics": "计算电路 Area 与 Delay 指标 (支持 Liberty 库)",
	"recipe": {
		"generate": "自动生成逻辑综合优化序列 (recipes)",
	},
	"run": "🚀 执行已拼装的命令串",
	"cancel": "❌ 放弃并退出构建器",
}
