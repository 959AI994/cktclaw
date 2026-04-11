"""
Reverse Handler — /reverse command

Runs the full AIG → PT → Verilog → Validate → Analyze pipeline.
Two-step guide: if no path is provided, prompt for a file path with PathCompleter.
"""

import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.styles import Style as PromptStyle
from rich.console import Console
from rich import print as rprint
import os

from .aig_handler import process_aig


async def process_reverse(args: str, cli_state) -> None:
	"""
	Guide + dispatch to the underlying AIG pipeline.
	"""
	path_arg = args.strip()
	console: Console = cli_state.console

	if not path_arg:
		# Ask for path interactively with path completion (loop with defensive intercepts)
		style_shim = PromptStyle.from_dict({
			'placeholder': 'fg:#222222 italic',
			'completion-menu': 'bg:default',
			'completion-menu.completion': 'fg:#56b6c2 bg:default',
			'completion-menu.completion.current': 'bg:#2c313a fg:#ffffff bold',
			'completion-menu.meta.completion': 'fg:#5c6370 bg:default',
			'completion-menu.meta.completion.current': 'bg:#2c313a fg:#abb2bf',
		})
		session = PromptSession(
			complete_while_typing=True,
			style=style_shim,
		)
		while True:
			try:
				text = (await session.prompt_async(
					HTML('<ansicyan>CktClaw</ansicyan> <ansigreen>[reverse]</ansigreen> ❯ '),
					completer=PathCompleter(expanduser=True),
					placeholder=" <请选择 .aig 文件路径>",
				)).strip()
			except (KeyboardInterrupt, EOFError):
				# Cancelled by user
				return

			if not text:
				continue

			# ── 顶级指令拦截层 ─────────────────────────────────
			raw = text.strip()
			# 1) 优先拦截回退
			if raw in ("..", "cd ..", "/back"):
				# 在 [reverse] 根层，直接退出回主 REPL
				return
			# 2) 优先拦截退出
			if raw in ("/exit", "exit"):
				raise SystemExit(0)

			# 到这里才做路径校验（防止把系统指令当路径）
			if not os.path.exists(raw):
				rprint("[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 回退[/bold yellow]")
				continue

			path_arg = raw
			break

	# Delegate to original AIG pipeline
	await process_aig(path_arg, cli_state)

