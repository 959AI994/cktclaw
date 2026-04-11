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

# DeepSeek API configuration (from webapp config if available)
try:
    from webapp.backend.config import DEEPSEEK_CONFIG
except ImportError:
    DEEPSEEK_CONFIG = {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "sk-af52153ce10d4453abf859151ea6ef05"),
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "timeout": 120,
        "temperature": 0.3,
        "max_tokens": 2000,
    }

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
  /about                    查看 CktClaw 平台简介与能力矩阵
  /clear                    创建新会话，清除屏幕
  /session info             显示当前会话信息
  /sessions list            列出最近的会话
  /help, /?                 显示此帮助信息
  /exit, /quit              退出程序（或按 Ctrl+C）

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
