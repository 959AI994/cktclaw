"""
AI4EDA Data Toolkit Builder — /ai4eda

Interactive, nested sub-command builder for AI4EDA-OpenABC-Data-Toolkit.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Union

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PromptStyle, merge_styles

from ..ui import render_spinner, render_error, Icons
from ..eda_tools.tool_dicts import AI4EDA_COMMANDS
from ..eda_tools.base_runner import clean_eda_output
from .. import config
from .abc_handler import _persist_cli_turn

AI4EDA_BIN = config.AI4EDA_TOOLKIT_PATH

GHOST_HINTS = {
	"convert aig2pt": " <input.aig> <output.pt> (示例: test.aig out.pt)",
	"convert aig2bench": " <input.aig> <output.bench>",
	"convert bench2graphml": " <input.bench> <output.graphml>",
	"convert graphml2pt": " <input.graphml> <output.pt>",
	"convert verilog2aig": " <input.v> <output.aig> [--top-module top]",
	"convert verilog2pt": " <input.v> <output.pt> [--top-module top]",
	"metrics": " <input.(aig|bench)> --lib <asap7.lib>",
	"recipe generate": " <input.aig> <output_dir> --num-recipes 100"
}


class AI4EDACompleter(Completer):
	"""
	Stage-aware completer driven by pending_tokens:
	- []: suggest top-level commands (convert, metrics, recipe, run, cancel)
	- ['convert']: suggest subcommands (aig2bench, aig2pt, ...)
	- ['recipe']: suggest subcommands (generate)
	- ['metrics'] or ['convert', <sub>] or ['recipe','generate']: PathCompleter is used instead
	"""

	def __init__(self, tree: Dict[str, Union[str, Dict[str, str]]], pending_tokens: list[str]):
		self.tree = tree
		self.pending_tokens = pending_tokens

	def get_completions(self, document, complete_event):
		text = (document.text_before_cursor or "")
		text_stripped = text.strip()
		# Auto-strip a leading slash in typed prefix for matching
		if text_stripped.startswith('/'):
			text_stripped = text_stripped.lstrip('/')

		stage = list(self.pending_tokens)

		def emit_candidates(cands: Dict[str, Union[str, Dict[str, str]]], prefix: str):
			for key, val in cands.items():
				if key.startswith(prefix):
					desc = val if isinstance(val, str) else "子命令..."
					yield Completion(key, start_position=-len(prefix), display=key, display_meta=desc)

		# Stage: no tokens yet → top-level
		if len(stage) == 0:
			prefix = text_stripped
			yield from emit_candidates(self.tree, prefix)
			return

		# Stage: after 'convert' → subcommands
		if len(stage) == 1 and stage[0] == "convert":
			node = self.tree.get("convert", {})
			if isinstance(node, dict):
				prefix = text_stripped
				yield from emit_candidates(node, prefix)
			return

		# Stage: after 'recipe' → subcommands
		if len(stage) == 1 and stage[0] == "recipe":
			node = self.tree.get("recipe", {})
			if isinstance(node, dict):
				prefix = text_stripped
				yield from emit_candidates(node, prefix)
			return

		# Other stages → handled by PathCompleter (no suggestions here)
		return


def handle_ai4eda(args: str, cli_state) -> None:
	console: Console = cli_state.console
	cmd_buffer: list[str] = []  # assembled command tokens for current command
	pending_tokens: list[str] = []  # e.g., ['convert'], ['convert','aig2pt']
	args_buffer: list[str] = []  # collects positional args for current command (e.g., input, output)

	# Toolbar preview
	def get_toolbar():
		# Color confirmed tokens (commands) in cyan, pending args in yellow
		confirmed = " ".join(cmd_buffer) if cmd_buffer else " ".join(pending_tokens)
		args = " ".join(args_buffer)
		confirmed_html = f'<ansicyan>{confirmed}</ansicyan>' if confirmed else "(空)"
		args_html = f' <ansiyellow>{args}</ansiyellow>' if args else ""
		return HTML(
			f'<style bg="ansiblack" fg="ansiyellow"> [当前脚本]: {confirmed_html}{args_html}  '
			f'(示例: convert aig2pt ./in.aig out.pt | run 执行，cancel 或 .. 回退) </style>'
		)

	# Key bindings: force popup completion on '/' key within AI4EDA builder
	kb = KeyBindings()

	@kb.add('/')
	def _(event):
		"""Insert '/' and force immediate completion popup without selecting first."""
		event.app.current_buffer.insert_text('/')
		event.app.current_buffer.start_completion(select_first=False)

	# Style aligned to global cli_style (transparent menu with accent colors)
	cli_style = PromptStyle.from_dict({
		'completion-menu': 'bg:default',
		'completion-menu.completion': 'fg:#56b6c2 bg:default',
		'completion-menu.completion.current': 'bg:#2c313a fg:#ffffff bold',
		'completion-menu.meta.completion': 'fg:#5c6370 bg:default',
		'completion-menu.meta.completion.current': 'bg:#2c313a fg:#abb2bf',
	})

	session = PromptSession(complete_while_typing=True, bottom_toolbar=get_toolbar, key_bindings=kb, style=cli_style)
	cmd_completer = AI4EDACompleter(AI4EDA_COMMANDS, pending_tokens)
	path_completer = PathCompleter(expanduser=True)

	# Helper: execute current buffer via external toolkit and render + memory
	def _execute_current():
		if not cmd_buffer:
			console.print("[dim]没有可执行的命令，请先选择子命令与参数[/dim]")
			return
		# Normalize argv to absolute paths where applicable
		argv = list(cmd_buffer)
		if len(argv) >= 3 and argv[0] == "convert":
			# input
			if len(argv) >= 3 and argv[2]:
				if not os.path.isabs(argv[2]):
					argv[2] = os.path.abspath(argv[2])
			# output
			if len(argv) >= 4 and argv[3]:
				if not os.path.isabs(argv[3]):
					argv[3] = os.path.abspath(argv[3])
		with render_spinner(console, f"{Icons.LIGHTNING} Running AI4EDA Toolkit..."):
			try:
				result = subprocess.run(
					[AI4EDA_BIN] + argv,
					capture_output=True,
					text=True,
					timeout=300,
				)
				stdout = result.stdout or ""
				stderr = result.stderr or ""
				combined = (stdout + ("\n" + stderr if stderr.strip() else "")).strip()
				cleaned = clean_eda_output("AI4EDA", combined)
			except FileNotFoundError:
				render_error(console, f"找不到可执行文件: {AI4EDA_BIN}", error_type="error")
				return
			except Exception as e:
				render_error(console, f"运行出错: {e}", error_type="error")
				return

		# Detect success and potential output path
		success = (result.returncode == 0 and not re.search(r'error', stderr or "", re.IGNORECASE))
		output_path = ""
		if len(argv) >= 4 and argv[0] == "convert":
			# convert subcommands pattern: convert <sub> <input> <output>
			output_path = argv[3]

		# Memory integration
		try:
			user_text = f"[用户手动执行了 AI4EDA 脚本]:\n{' '.join(argv)}"
			if success and output_path:
				assistant_text = f"[AI4EDA 执行结果]:\n✅ 转换成功！生成的文件位于: {output_path}\n\n{cleaned or ''}".strip()
			else:
				assistant_text = f"[AI4EDA 执行结果]:\n{cleaned or '(无输出)'}"
			_persist_cli_turn(cli_state, user_text, assistant_text)
		except Exception:
			pass

		# Render output
		if success and output_path:
			console.print(
				Panel(
					Text(f"✅ 转换成功！生成的文件位于: {output_path}\n\n{cleaned or ''}".strip(), style="green"),
					title="[bold yellow]AI4EDA Toolkit Output[/bold yellow]",
					border_style="yellow",
					box=ROUNDED,
					padding=(0, 1),
					expand=False,
				)
			)
		else:
			console.print(
				Panel(
					Text(f"❌ 转换失败，请检查路径或文件格式。\n\n{combined or '(无输出)'}", style="red"),
					title="[bold red]AI4EDA Toolkit Error[/bold red]",
					border_style="red",
					box=ROUNDED,
					padding=(0, 1),
					expand=False,
				)
			)

	def _build_prompt():
		# CktClaw [ai4eda][convert][aig2pt] ❯
		segments = ["[ai4eda]"] + [f"[{tok}]" for tok in pending_tokens]
		ctx = "".join(segments)
		return HTML(f'<ansicyan>CktClaw</ansicyan> <ansigreen>{ctx}</ansigreen> ❯ ')

	def _args_complete() -> bool:
		return len(cmd_buffer) >= 4 and cmd_buffer[0] == "convert"

	while True:
		try:
			# Dynamic prompt & completer based on pending
			if len(pending_tokens) == 0:
				# Placeholder at top-level (suggest main verbs)
				prompt = _build_prompt()
				line = session.prompt(prompt, completer=cmd_completer, placeholder=" 选择 convert/metrics/recipe …").strip()
			elif len(pending_tokens) == 1 and pending_tokens[0] == "convert":
				# still suggest convert subcommands
				prompt = _build_prompt()
				line = session.prompt(prompt, completer=cmd_completer, placeholder=" 选择子命令: aig2pt / verilog2aig / …").strip()
			elif len(pending_tokens) == 1 and pending_tokens[0] == "recipe":
				prompt = _build_prompt()
				line = session.prompt(prompt, completer=cmd_completer, placeholder=GHOST_HINTS.get("recipe generate", "")).strip()
			else:
				# after full command determined -> path/args
				ctx = " ".join(pending_tokens)
				prompt = _build_prompt()
				ph = " ✅ 参数已齐，请输入 run 执行命令 " if _args_complete() else GHOST_HINTS.get(ctx, "")
				line = session.prompt(prompt, completer=path_completer, placeholder=ph).strip()
		except (KeyboardInterrupt, EOFError):
			return

		if not line:
			# If args are complete, guide user
			if _args_complete():
				console.print("[yellow]请输入 run 执行或 .. 回退[/yellow]")
			continue

		# Backtrack support: '..' or 'cd ..'
		if line == ".." or line.lower().strip() == "cd ..":
			# Prefer popping args first, then pending tokens, then last of cmd_buffer
			if args_buffer:
				args_buffer.pop()
			elif pending_tokens:
				pending_tokens.pop()
				# sync cmd_buffer to pending
				cmd_buffer[:] = pending_tokens[:]
			else:
				# already at root [ai4eda] -> exit builder
				return
			# loop to re-render prompt/completer
			continue

		# Smart leading slash handling: only strip when expecting a command token and it matches keys
		def _maybe_strip_leading_slash(token: str, expecting_command: bool) -> str:
			if expecting_command and token.startswith("/"):
				cand = token.lstrip("/")
				# valid keys for current stage
				if len(pending_tokens) == 0:
					valid = set(AI4EDA_COMMANDS.keys())
				elif len(pending_tokens) == 1 and pending_tokens[0] in ("convert", "recipe"):
					node = AI4EDA_COMMANDS.get(pending_tokens[0], {})
					valid = set(node.keys()) if isinstance(node, dict) else set()
				else:
					valid = set()
				if cand in valid:
					return cand
			return token

		# ── Global high-priority intercepts ───────────────────────
		lt = line.lower()
		if lt == "run":
			# Only execute if current command is fully assembled; if not, guide user
			if pending_tokens and cmd_buffer[:len(pending_tokens)] != pending_tokens:
				# sync tokens if needed
				cmd_buffer[:] = pending_tokens + args_buffer
			# For convert subcommands, require two args (input, output)
			if len(cmd_buffer) >= 2 and cmd_buffer[0] == "convert":
				if len(cmd_buffer) < 4:
					console.print("[yellow]需要输入 Input 与 Output 路径后再执行（示例: convert aig2pt in.aig out.pt）[/yellow]")
					continue
			_execute_current()
			# Do not exit; reset state and stay in builder root
			cmd_buffer.clear()
			pending_tokens.clear()
			args_buffer.clear()
			continue

		# allow run/cancel at any time when not pending
		# cancel 已废弃；run 在上方统一处理

		# When not pending: parse top-level or nested top+sub
		if len(pending_tokens) == 0:
			parts = line.split()
			if not parts:
				continue
			top = _maybe_strip_leading_slash(parts[0], expecting_command=True)
			# Validate top-level command
			valid_top = set(AI4EDA_COMMANDS.keys())
			if top not in valid_top:
				console.print("[bold red]✗ 非法指令，请从菜单中选择或输入 .. 回退[/bold red]")
				continue
			node = AI4EDA_COMMANDS.get(top)
			if isinstance(node, dict):
				# Expect a subcommand next
				pending_tokens[:] = [top]
				cmd_buffer[:] = [top]
				args_buffer.clear()
				# If user provided subcommand inline, accept it
				if len(parts) >= 2:
					sub = _maybe_strip_leading_slash(parts[1], expecting_command=True)
					# Validate convert/recipe subcommand
					if sub not in node.keys():
						console.print("[bold red]✗ 非法指令，请从菜单中选择或输入 .. 回退[/bold red]")
						continue
					cmd_buffer.append(sub)
					pending_tokens.append(sub)
				continue
			else:
				# Leaf like 'metrics' or unstructured; proceed to args stage
				pending_tokens[:] = [top]
				cmd_buffer[:] = [top]
				args_buffer.clear()
				continue
		else:
			# pending present:
			if len(pending_tokens) == 1 and pending_tokens[0] in ("convert", "recipe"):
				# This line should be subcommand
				sub = _maybe_strip_leading_slash(line.split()[0], expecting_command=True)
				# Validate subcommand
				node = AI4EDA_COMMANDS.get(pending_tokens[0], {})
				if not (isinstance(node, dict) and sub in node.keys()):
					console.print("[bold red]✗ 非法指令，请从菜单中选择或输入 .. 回退[/bold red]")
					continue
				cmd_buffer.append(sub)
				pending_tokens.append(sub)
				args_buffer.clear()
				continue
			# Arguments/paths collection phase
			if pending_tokens[0] == "convert" and len(pending_tokens) == 2:
				# Need two positional args: input then output
				if len(args_buffer) == 0:
					# Collect input
					inp = line
					if not os.path.isabs(inp):
						inp = os.path.abspath(inp)
					# Input must exist
					if not os.path.exists(inp):
						console.print("[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 重新选择命令[/bold yellow]")
						continue
					args_buffer.append(inp)
					# Prompt will loop; next time we are still in args stage, collect output
					continue
				elif len(args_buffer) == 1:
					# Collect output, assemble full command
					outp = line
					if not os.path.isabs(outp):
						outp = os.path.abspath(outp)
					# If output is a directory, auto-compose filename from input
					if os.path.isdir(outp):
						inp_name = Path(args_buffer[0]).stem
						subcmd = pending_tokens[1]
						ext_map = {
							"aig2bench": ".bench",
							"bench2graphml": ".graphml",
							"graphml2pt": ".pt",
							"verilog2aig": ".aig",
							"aig2pt": ".pt",
							"verilog2pt": ".pt",
						}
						ext = ext_map.get(subcmd, "")
						outp = str(Path(outp) / f"{inp_name}{ext}")
					else:
						# Parent dir must exist
						parent = str(Path(outp).parent)
						if parent and not os.path.exists(parent):
							console.print("[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 重新选择命令[/bold yellow]")
							continue
					args_buffer.append(outp)
					cmd_buffer[:] = pending_tokens + args_buffer  # convert sub in out
					# Command fully assembled; reset pending to allow 'run' or more operations
					pending_tokens.clear()
					args_buffer.clear()
					continue
				else:
					# Extra args: append
					extras = [os.path.abspath(tok) if not os.path.isabs(tok) else tok for tok in line.split()]
					cmd_buffer.extend(extras)
					pending_tokens.clear()
					args_buffer.clear()
					continue
			else:
				# Generic case: accept any number of args, then allow run
				if line:
					toks = [os.path.abspath(tok) if not os.path.isabs(tok) else tok for tok in line.split()]
					args_buffer.extend(toks)
					cmd_buffer[:] = pending_tokens + args_buffer
				# Keep pending to accept more args or let user 'run'
				continue

