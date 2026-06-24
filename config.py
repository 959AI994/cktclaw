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

_REPO_ROOT = Path(__file__).resolve().parent

# ━━━━━━━━━━ Database Configuration ━━━━━━━━━━
# Isolated CLI database (separate from webapp)
CLI_DATABASE_PATH = str(Path(__file__).parent / "cktclaw_sessions.db")

# ━━━━━━━━━━ Engine Configuration ━━━━━━━━━━
DEFAULT_ENGINE = "deepseek"  # "deepseek", "logicrt", or "qwen"
AVAILABLE_ENGINES = ["deepseek", "logicrt", "qwen"]

# ━━━━━━━━━━ Memory Management ━━━━━━━━━━
MAX_MEMORY_ROUNDS = 5  # Sliding window size for short memory
CONTEXT_WINDOW_SIZE = 16384  # Max tokens for context (CodeV/DeepSeek)

# Semantic embedding backend: auto | jina | bge | minilm
# auto: Jina API when JINA_API_KEY is set, else local BGE
EMBEDDING_BACKEND = os.environ.get("CKTCLAW_EMBEDDING_BACKEND", "auto")
# Optional model override (e.g. jina-embeddings-v3, BAAI/bge-small-zh-v1.5)
EMBEDDING_MODEL = os.environ.get("CKTCLAW_EMBEDDING_MODEL", "")

# ━━━━━━━━━━ Model Configuration ━━━━━━━━━━
DEFAULT_MAX_TOKENS = 2000  # Max tokens for generation
INFERENCE_TIMEOUT = 300  # 5 minutes timeout for long AIG processing

# Local chat model configuration (supports HuggingFace Hub ID or local path)
LOCAL_CHAT_MODEL = os.environ.get("CKTCLAW_LOCAL_MODEL", "")

# Qwen local model path（仅使用 Instruct 对话版）
QWEN_MODEL_PATH = os.environ.get(
    "CKTCLAW_QWEN_PATH",
    str(_REPO_ROOT / "models" / "qwen" / "Qwen2.5-3B-Instruct"),
)
# Qwen GPU ID: -2 = auto-select, 0/1/… = fixed logical GPU
QWEN_GPU_ID = int(os.environ.get("CKTCLAW_QWEN_GPU", "-2"))

# CodeV model configuration（对话 / 分析用本地 CodeV）
# 优先级: 环境变量 CKTCLAW_CODEV_PATH → LOCAL_CHAT_MODEL → 并排的 GenEDA CodeV 目录 → 本仓库 models/llm_decoder/CodeV
_GENEDA_CODEV = (
    _REPO_ROOT.parent
    / "0reverse"
    / "GenEDA-main"
    / "reverse_engineering"
    / "models"
    / "llm_decoder"
    / "CodeV"
)
_REPO_BUNDLED_CODEV = _REPO_ROOT / "models" / "llm_decoder" / "CodeV"
if os.environ.get("CKTCLAW_CODEV_PATH"):
    CODEV_PATH = os.environ["CKTCLAW_CODEV_PATH"]
elif LOCAL_CHAT_MODEL:
    # Use LOCAL_CHAT_MODEL if specified (supports HF Hub ID like "Qwen/Qwen3.5-2B")
    CODEV_PATH = LOCAL_CHAT_MODEL
elif _GENEDA_CODEV.is_dir():
    CODEV_PATH = str(_GENEDA_CODEV.resolve())
else:
    CODEV_PATH = str(_REPO_BUNDLED_CODEV.resolve())
# 对话懒加载用：-2 = 自动选择显存 ≥2GB 的可见 GPU；0/1/… = 固定逻辑 GPU
CODEV_CHAT_GPU_ID = int(os.environ.get("CKTCLAW_CODEV_CHAT_GPU", "-2"))
# 其它子系统（如历史脚本）仍可用的逻辑 GPU编号
CODEV_GPU_ID = int(os.environ.get("CKTCLAW_CODEV_GPU", "1"))

# LogicRT inference configuration
LOGICRT_CHECKPOINT = "output/full_training_norm/dpo_batch_20260319_103708/checkpoint-200"
LOGICRT_GPU_ID = 0  # Logical GPU ID for LogicRT inference (maps to physical GPU 2)
LOGICRT_AIG_ENCODER = "mgvga_improved"

# DeepSeek API configuration — api_key is NOT stored here.
# Use cktclaw.api_credentials.get_deepseek_api_key() to resolve the key.
DEEPSEEK_CONFIG = {
    # "api_key" intentionally absent — never hardcode here
    "base_url": "https://api.deepseek.com",
    "default_model": "deepseek-chat",
    "timeout": 120,
    "temperature": 0.3,
    "max_tokens": 2000,
}

# ━━━━━━━━━━ AI4EDA Toolkit Configuration ━━━━━━━━━━
# Resolved from env; empty when unset (consumers must error clearly rather than
# silently falling back to a hard-coded absolute path).
AI4EDA_TOOLKIT_PATH = os.environ.get("CKTCLAW_AI4EDA_PATH", "")

# ABC executable — env override, else yosys-abc / abc discovered on PATH.
ABC_PATH = os.environ.get("ABC_PATH")

if not ABC_PATH:
    import shutil as _shutil
    ABC_PATH = _shutil.which("yosys-abc") or _shutil.which("abc") or "abc"
AI4EDA_DEFAULT_LIB = os.environ.get(
    "AI4EDA_DEFAULT_LIB",
    str(Path(AI4EDA_TOOLKIT_PATH) / "libs" / "asap7.lib"),
)

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
    "MEMORY SOURCE OF TRUTH (MANDATORY):\n"
    "- Session memory is stored in cktmem/SQLite, not in MEMORY.md files.\n"
    "- Do NOT claim you inspected MEMORY.md or a memory directory unless a tool output explicitly contains it.\n"
    "- When user asks what you remember, first use 'list_session_memory' to check saved memory entries.\n\n"
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
    "TOOL OUTPUT & BREVITY (MANDATORY — concise English summary, minimal tool rounds):\n"
    "- Once a tool returns area, delay, power, or other metrics, provide a concise **English** summary in the next turn, "
    "explicitly stating the key values and their meaning. Do not only paste raw logs without explanation.\n"
    "- For the same tool category (ai4eda, yosys, abc, opensta, reverse), if you already obtained usable output, "
    "**do not call the same category again** unless the user provides a new goal or explicit error-correction request.\n"
    "- Default strategy: finish the task in the fewest turns; if one tool call is enough, do not make multiple calls.\n\n"
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
# 仅反映当前进程环境；默认不隐式限制（main 不再写死 2,3,4,5）
CUDA_VISIBLE_DEVICES = os.environ.get("CUDA_VISIBLE_DEVICES", "")

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
  /sessions clear           删除当前项目下除当前会话外的所有会话（需输入 DELETE 确认）
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

CHIP DESIGN DOMAINS 芯片设计领域 (digital-chip-design-agents):
  /chip-design-skills         进入芯片设计子终端（提示符 [chip-design-skills] / [chip-*]；.. 回主界面）
  /chip-architecture [task]   微架构探索、PPA 估算、风险评估
  /chip-rtl [task]            SystemVerilog RTL 设计、lint、CDC 检查
  /chip-verification [task]   UVM 验证、覆盖率收敛、回归测试
  /chip-formal [task]         形式验证 FPV、等价性检查 LEC
  /chip-synthesis [task]      逻辑综合、SDC 约束、网表 QC
  /chip-dft [task]            可测性设计、扫描插入、ATPG
  /chip-sta [task]            静态时序分析、多角分析、ECO 指导
  /chip-hls [task]            高层次综合 C/C++ → RTL
  /chip-pd [task]             物理设计：布图→布线→签核
  /chip-soc [task]            SoC IP 集成、总线结构、芯片级仿真
  /chip-compiler [task]       编译器工具链 LLVM/GCC 后端
  /chip-firmware [task]       嵌入式固件 BSP、驱动、RTOS
  /chip-fpga [task]           FPGA 仿真移植、分区、上板验证
  /chip-infrastructure [task] EDA 工具检测、wrapper 部署、MCP 配置

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# 与 main.parse_input 中的 chip-* 名称一致（仅全称，无短别名）
CHIP_DESIGN_SLASH_ROWS: list[tuple[str, str]] = [
    ("chip-architecture", "微架构、PPA、风险评估"),
    ("chip-rtl", "RTL 设计、lint、CDC"),
    ("chip-verification", "UVM、覆盖率、回归"),
    ("chip-formal", "形式验证 FPV、LEC"),
    ("chip-synthesis", "逻辑综合、SDC、网表 QC"),
    ("chip-dft", "DFT、扫描、ATPG"),
    ("chip-sta", "静态时序 STA、多角、ECO"),
    ("chip-hls", "高层次综合 HLS"),
    ("chip-pd", "物理设计 PD"),
    ("chip-soc", "SoC 集成"),
    ("chip-compiler", "编译器工具链"),
    ("chip-firmware", "固件、BSP、RTOS"),
    ("chip-fpga", "FPGA 移植与验证"),
    ("chip-infrastructure", "EDA 检测、wrapper、MCP"),
]

CHIP_DESIGN_SKILL_NAMES: frozenset[str] = frozenset(p for p, _ in CHIP_DESIGN_SLASH_ROWS)
