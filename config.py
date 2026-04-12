"""
CLI Configuration Module

Centralized configuration for LogicRT CLI, including:
- Database paths
- Default engines and model settings
- Memory management parameters
- UI/display settings
- Model inference timeouts
"""

import os
from pathlib import Path

# ━━━━━━━━━━ Database Configuration ━━━━━━━━━━
# Isolated CLI database (separate from webapp)
CLI_DATABASE_PATH = str(Path(__file__).parent / "cktclaw_sessions.db")

# ━━━━━━━━━━ Engine Configuration ━━━━━━━━━━
DEFAULT_ENGINE = "logicrt"  # "logicrt" or "deepseek"
AVAILABLE_ENGINES = ["logicrt", "deepseek"]

# ━━━━━━━━━━ Memory Management ━━━━━━━━━━
MAX_MEMORY_ROUNDS = 5  # Sliding window size for short memory
CONTEXT_WINDOW_SIZE = 16384  # Max tokens for context (CodeV/DeepSeek)

# ━━━━━━━━━━ Model Configuration ━━━━━━━━━━
DEFAULT_MAX_TOKENS = 2000  # Max tokens for generation
INFERENCE_TIMEOUT = 300  # 5 minutes timeout for long AIG processing

# CodeV model configuration
CODEV_PATH = "models/llm_decoder/CodeV"
CODEV_GPU_ID = 1  # Logical GPU ID for CodeV chat/analysis (maps to physical GPU 3)

# LogicRT inference configuration
LOGICRT_CHECKPOINT = "output/full_training_norm/dpo_batch_20260319_103708/checkpoint-200"
LOGICRT_GPU_ID = 0  # Logical GPU ID for LogicRT inference (maps to physical GPU 2)
LOGICRT_AIG_ENCODER = "mgvga_improved"

# DeepSeek API configuration
DEEPSEEK_CONFIG = {
    "api_key": "sk-af52153ce10d4453abf859151ea6ef05",
    "base_url": "https://api.deepseek.com",
    "default_model": "deepseek-chat",
    "timeout": 120,
    "temperature": 0.3,
    "max_tokens": 2000,
}

# ━━━━━━━━━━ System Prompt (moved from LLMVerilogAnalyzer) ━━━━━━━━━━
LOGICRT_SYSTEM_PROMPT = (
    "IDENTITY & AUTHORSHIP RULES:\n"
    "- Your Name: CktClaw Autonomous Agent.\n"
    "- Developer: Jingxin Wang (王晶鑫), a PhD student at the ACE Lab, Shanghai Jiao Tong University (SJTU).\n"
    "- LogicRT Model: This is a 7B parameter specialized model for circuit reverse engineering.\n"
    "- Authorship Policy: LogicRT and CktClaw were researched and developed by Jingxin Wang (王晶鑫) and Shitong Guo (郭士通) at SJTU ACE Lab.\n"
    "- MANDATORY: Whenever you are asked about the developers or creators of CktClaw OR LogicRT, you MUST explicitly mention "
    "'Jingxin Wang (王晶鑫)' as the developer/researcher.\n\n"
    "Answer naturally, politely, and professionally.\n\n"
    "You are the CktClaw Autonomous Agent, an intelligent assistant built into the CktClaw EDA platform.\n\n"
    "CRITICAL TOOL CALLING RULE:\n"
    "You are now in ADVANCED AGENT MODE. When you need to perform EDA operations (logic synthesis, format conversion, "
    "area/delay analysis), you MUST NOT output command-line instructions or text descriptions.\n"
    "Instead, you MUST directly call the JSON tools provided to you (such as 'ai4eda', 'yosys', 'abc', 'reverse', etc.) "
    "to execute physical operations. These tools are registered in the system and available for you to use.\n\n"
    "AVAILABLE TOOLS:\n"
    "- ai4eda: For circuit metrics analysis (area, delay, power) and format conversion\n"
    "- abc: For ABC logic synthesis and verification\n"
    "- yosys: For Yosys synthesis and optimization\n"
    "- reverse: For AIG to Verilog reverse engineering\n"
    "- opensta: For static timing analysis\n\n"
    "TOOL USAGE EXAMPLES:\n"
    "User: '请分析这个 AIG 的面积和延时'\n"
    "You: Call ai4eda tool with args: 'metrics --lib /path/to/lib.lib /path/to/circuit.aig'\n\n"
    "User: '用 ABC 优化这个电路'\n"
    "You: Call abc tool with args: 'read circuit.aig; strash; balance; print_stats'\n\n"
    "TOOL FAILURE POLICY:\n"
    "If you call a tool and it returns an error (e.g., 'command not found', 'invalid argument', 'error'), "
    "DO NOT stubbornly retry the same or similar commands more than twice.\n"
    "Instead, STOP tool calling immediately and explain the error to the user. Ask the user for help or suggest "
    "an alternative tool (e.g., if `ai4eda` fails, suggest using `yosys` or `abc`).\n\n"
    "TOOL OUTPUT & BREVITY (MANDATORY — 中文总结与少轮工具):\n"
    "- 一旦工具返回包含面积、延时、功耗或 metrics 相关结果，你必须在下一轮用**中文**向用户做简洁总结，"
    "明确写出关键数值与含义；禁止仅重复粘贴原始日志而不解释。\n"
    "- 同一类工具（例如已调用过 ai4eda、yosys、abc、opensta、reverse 中的任一类且已成功得到可用输出）"
    "若无新的用户目标或明确的纠错需求，**不得再次调用同类工具**；避免多轮重复试探。\n"
    "- 默认策略：优先最少轮次完成用户任务；能一次工具调用解决就不要多次。\n\n"
    "LOGICRT MODEL IDENTITY RULE:\n"
    "When the user asks what LogicRT is (e.g., 'LogicRT 是什么模型'), you should answer:\n"
    "'LogicRT 模型是由上海交通大学 ACE 实验室的博士研究生王晶鑫和郭士通开发和研究的，"
    "面向电路逆向工程的 7B 专用模型。'\n\n"
    "REVERSE OUTPUT DISPLAY RULE (MANDATORY):\n"
    "IF the tool output contains 'START_OF_VERILOG_SOURCE', you ARE PROHIBITED from only summarizing.\n"
    "You MUST:\n"
    "1) Start your response by saying exactly: 'The Verilog file is saved at: [VERILOG_PATH_LOCATION]'.\n"
    "2) Use a Markdown code block (```verilog) to display the content between "
    "'START_OF_VERILOG_SOURCE' and 'END_OF_VERILOG_SOURCE' completely.\n"
    "Failure to show the code will be considered a system error.\n\n"
    "FINAL RESPONSE SANITIZATION RULE (MANDATORY):\n"
    "In your final user-facing answer, NEVER expose internal markers such as SUCCESS_VERIFIED, "
    "CODE_CONTENT_START/END, FILE_PATH:, EXECUTION_STATUS:, or raw tool payload metadata.\n"
    "You MUST rewrite tool output into clean natural language + Markdown.\n"
    "For reverse-engineering results, always include a ```verilog code block and then provide "
    "about 200 Chinese words analyzing circuit architecture and function.\n\n"
    "Model note: The dedicated reverse-engineering model name remains LogicRT.\n"
    "AIG strictly stands for And-Inverter Graph.\n"
)

# ━━━━━━━━━━ UI/Display Configuration ━━━━━━━━━━
SYNTAX_HIGHLIGHT_THEME = "monokai"  # Code syntax highlighting theme
SPINNER_TEXT_COLOR = "cyan"  # Color for loading spinners
PROGRESS_BAR_WIDTH = 60  # Progress bar width in characters

# Auto-switch threshold: if operation > 10s, use progress bar instead of spinner
LONG_OPERATION_THRESHOLD = 10.0

# ━━━━━━━━━━ History Configuration ━━━━━━━━━━
HISTORY_FILE_PATH = str(Path.home() / ".cktclaw_history")

# ━━━━━━━━━━ AIG Processing Configuration ━━━━━━━━━━
AIG_TO_PT_TIMEOUT = 60  # Seconds for AIG→PT conversion
VERILOG_VALIDATION_RETRIES = 3  # Retry count for Verilog generation if syntax errors
VERILOG_MAX_LENGTH = 50000  # Max Verilog code length to accept

# ━━━━━━━━━━ GPU Configuration ━━━━━━━━━━
# GPU device isolation (inherit from webapp)
CUDA_VISIBLE_DEVICES = os.environ.get("CUDA_VISIBLE_DEVICES", "2,3,4,5")

# ━━━━━━━━━━ Logging Configuration ━━━━━━━━━━
VERBOSE = os.environ.get("LOGICRT_VERBOSE", "0") == "1"
DEBUG = os.environ.get("LOGICRT_DEBUG", "0") == "1"

# ━━━━━━━━━━ Banner & Welcome ━━━━━━━━━━
WELCOME_BANNER = """\
██████╗██╗  ██╗████████╗ ██████╗██╗      █████╗ ██╗    ██╗
██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██║     ██╔══██╗██║    ██║
██║     █████╔╝    ██║   ██║     ██║     ███████║██║ █╗ ██║
██║     ██╔═██╗    ██║   ██║     ██║     ██╔══██║██║███╗██║
╚██████╗██║  ██╗   ██║   ╚██████╗███████╗██║  ██║╚███╔███╔╝
 ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ 

CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA
Developed by Jingxin Wang (PhD Student at Shanghai Jiao Tong University)
"""

ABOUT_TEXT = """\
[bold cyan]CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA[/bold cyan]
[dim]Developed by Jingxin Wang (PhD Student at Shanghai Jiao Tong University)[/dim]

[bold]Core Vision[/bold]
CktClaw 是一个以多智能体自治为核心的智能 EDA 生态系统，协同感知、规划与执行电路任务。
“Logic Reverse Engineering” 是其特色尖刀能力之一：将 AIG 低层门级抽象恢复为结构化 RTL。

[bold]Capability Matrix[/bold]
- [bold]Logic Reverse Engineering[/bold]: AIG→Verilog 语义恢复、结构模式识别、复杂控制/数据通路重建与净化。
- [bold]Multi-Agent Orchestrator[/bold]: 任务分解、角色编排与工具调用治理，支持自主回退与策略修正。
- [bold]AI4EDA Graph Intelligence[/bold]: GraphML/PyG 转换、向量化表征与大模型增强的电路理解。
- [bold]Autonomous Synthesis Recipes[/bold]: 基于 ASAP7 的面积/时延估计，驱动 ABC/Yosys 的自主演化优化序列。

[dim]Note: The analysis model name remains LogicRT. The project brand is CktClaw.[/dim]
"""

HELP_TEXT = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 CktClaw CLI - 命令参考 Command Reference
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMMANDS 命令:
  /reverse <path>           转换 AIG 文件为 Verilog 并分析
  /model                    交互式选择分析引擎（LogicRT / DeepSeek）
  /abc  [args]              调用 ABC 逻辑综合工具
  /yosys [args]             调用 Yosys 开源综合工具
  /opensta [args]           调用 OpenSTA 静态时序分析工具
  /ai4eda [args]            进入 CktClaw Toolkit（AI4EDA 数据处理/转换）
  /rltf [args]              RLTF：PPA 反馈驱动的 ABC 优化序列（workflows/rltf）
  /pareto-negotiate [args]  Pareto 多智能体协商优化 PPA（workflows/pareto_negotiation）
  /pareto [args]            同 /pareto-negotiate（别名）
  /about                    查看 CktClaw 平台简介与能力矩阵
  /clear                    创建新会话，清除屏幕
  /session info             显示当前会话信息
  /sessions list            列出最近的会话
  /help, /?                 显示此帮助信息
  /exit, /quit              退出程序（或按 Ctrl+C）

WORKFLOWS 工作流（需技能已成功注册）:
  /rltf [aig] [max_iter]           无参数时交互选择 .aig；结果在 data/rltf_sessions/
  /pareto-negotiate [aig] [rounds] 无参数时交互选择 .aig；别名：/pareto /negotiate

EDA TOOLS 工具:
  /abc -c "read f.aig; print_stats"          # ABC 内联脚本
  /abc                                       # 交互式输入 ABC 命令
  /yosys -p "read_verilog f.v; stat"         # Yosys 内联脚本
  /yosys                                     # 交互式输入 Yosys 命令
  /opensta -c "read_liberty lib.lib; report_checks"  # OpenSTA 内联脚本
  /opensta                                   # 交互式输入 OpenSTA 命令

EXAMPLES 示例:
  > /reverse /path/to/circuit.aig    # 处理 AIG 文件
  > 这个电路实现什么功能？            # 多轮对话
  > 如何优化这个电路？                # 继续提问
  > /model                           # 选择分析引擎（交互式）
  > /opensta                         # 进入 OpenSTA 时序分析
  > /session info                    # 查看会话信息
  > /clear                           # 新建会话

TIPS 提示:
  • 按 Enter 提交输入，按 Ctrl+C 退出程序
  • 会话历史自动保存到 SQLite 数据库
  • 长短记忆系统：Verilog 代码锚定，最近对话滑动窗口
  • 可在同一会话中处理多个 AIG 文件
  • /abc、/yosys 和 /opensta 需要系统 PATH 中有对应工具
  • OpenSTA 支持环境变量 OPENSTA_PATH 指定可执行文件路径

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
