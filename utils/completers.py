from prompt_toolkit.completion import Completer, Completion

GLOBAL_COMMANDS = {
	"/reverse": "🚀 核心流：将 AIG 逆向工程为 Verilog",
	"/yosys": "🛠️ 进入 Yosys 逻辑综合与优化交互模式",
	"/abc": "🛠️ 进入 ABC 逻辑综合与验证交互模式",
	"/model": "🔀 切换当前分析引擎 (LogicRT / DeepSeek)",
	"/clear": "🧹 清屏并开启新的对话 Session",
	"/help": "📖 查看详细帮助文档",
	"/exit": "👋 退出 LogicRT 控制台",
}


class RootCommandCompleter(Completer):
	def get_completions(self, document, complete_event):
		text = document.text_before_cursor.lstrip()
		# 只要检测到以 / 开头，无视分词器规则，直接输出匹配项
		if text.startswith('/'):
			for cmd, desc in GLOBAL_COMMANDS.items():
				if cmd.startswith(text):
					yield Completion(
						cmd,
						start_position=-len(text),
						display=cmd,
						display_meta=desc
					)

