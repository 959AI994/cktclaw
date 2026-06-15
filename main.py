"""
LogicRT CLI - Main REPL Loop

Entry point and core REPL infrastructure for the LogicRT CLI.
Provides:
- CLIState: Global mutable state management
- REPL loop with command parsing and dispatching
- Prompt_toolkit integration for history and multiline support
- Graceful shutdown and error handling
"""

import sys
import os
import uuid
import asyncio
import warnings
import logging
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Any
from datetime import datetime


def _flush_stdin_typeahead() -> None:
    """丢弃 stdin 上尚未被读取的数据。

    在 Rich spinner / LLM 等待期间，终端仍会把按键回显到屏幕（与状态行糊在一起），
    若此时敲了回车，整行会留在缓冲区；下一轮 prompt_toolkit 会立刻把它当成新输入，
    从而误发第二条「聊天」、再次调用 DeepSeek（看起来像重复响应）。
    """
    try:
        import termios

        if not sys.stdin.isatty():
            return
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (ImportError, AttributeError, OSError, ValueError):
        pass

# ━━━━━━━━━━ Silence noisy third-party output BEFORE any library import ━━━━━━━━━━
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TQDM_DISABLE"] = "1"            # 禁用 tqdm 进度条 (Loading checkpoint shards 等)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("accelerate").setLevel(logging.ERROR)

# Ensure webapp modules can be imported
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# GPU 可见性：须在导入 torch 之前决定。
# 旧版默认写死 2,3,4,5，会导致 nvidia-smi 里空闲的 0/1 对 PyTorch 不可见；且若列表中含 ERR/故障卡，
# mem_get_info 可能异常，出现「明明有空卡却报无满足条件 GPU」。
# • 未设置时：不修改 CUDA_VISIBLE_DEVICES，由驱动暴露全部 GPU，LocalCodeV 按空闲显存自动选卡。
# • 需与实验室隔离策略一致时：export CKTCLAW_CUDA_VISIBLE_DEVICES=2,3,4,5
# • 或直接：export CUDA_VISIBLE_DEVICES=0,1,2,3（排除占满或故障卡）
if "CUDA_VISIBLE_DEVICES" not in os.environ:
    _iso = os.environ.get("CKTCLAW_CUDA_VISIBLE_DEVICES")
    if _iso is not None and str(_iso).strip() != "":
        os.environ["CUDA_VISIBLE_DEVICES"] = str(_iso).strip()

# Configure external EDA tool paths early (before handlers import)
_DEFAULT_ABC = "/home/wjx/abc/abc"
_DEFAULT_OPENSTA = "/home/wjx/OpenSTA/build/sta"

if "ABC_PATH" not in os.environ:
    try:
        from os import path, access, X_OK
        if path.exists(_DEFAULT_ABC) and access(_DEFAULT_ABC, X_OK):
            os.environ["ABC_PATH"] = _DEFAULT_ABC
    except Exception:
        pass

if "OPENSTA_PATH" not in os.environ:
    try:
        from os import path, access, X_OK
        if path.exists(_DEFAULT_OPENSTA) and access(_DEFAULT_OPENSTA, X_OK):
            os.environ["OPENSTA_PATH"] = _DEFAULT_OPENSTA
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.box import ROUNDED
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.key_binding import KeyBindings

from . import config
from .ui import (
    create_console,
    render_header,
    render_turn_separator,
    render_error,
    render_success,
    render_prompt,
    Icons,
)
from .handlers.ai4eda_handler import handle_ai4eda

# Import cktmem modules for context management
from .cktmem import (
    ContextManager,
    Storage,
    CompactConfig,
    MessageRole,
    MessageType,
    ContextLayer,
)

# Import Harness modules for architecture management
from .harness import (
    get_state_manager,
    get_task_manager,
    get_skill_registry,
    get_coordinator_manager,
    CoordinatorMode,
)

# Keep old imports for backward compatibility (optional fallback)
try:
    from webapp.memory.db_manager import MemoryManager
    from webapp.memory.context_builder import ContextBuilder
    LEGACY_MEMORY_AVAILABLE = True
except ImportError:
    LEGACY_MEMORY_AVAILABLE = False

# Note: LLMVerilogAnalyzer and LogicRTInferencer are imported lazily in handlers
# Import type stubs for annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cktclaw.models import LLMVerilogAnalyzer
    from cktclaw.models.logicrt_inferencer import LogicRTInferencer


# ━━━━━━━━━━ Global State Management ━━━━━━━━━━
@dataclass
class CLIState:
    """
    Global mutable state for the REPL.
    Manages session, engine, and loaded models.
    """
    # Session management
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Engine configuration
    current_engine: str = field(default=config.DEFAULT_ENGINE)

    # CktMem managers (new architecture)
    storage: Optional[Storage] = None
    context_manager: Optional[ContextManager] = None

    # Harness managers (architecture core)
    harness_state_manager: Optional[Any] = None  # StateManager from harness.bootstrap
    harness_task_manager: Optional[Any] = None   # TaskManager from harness.tasks
    harness_skill_registry: Optional[Any] = None  # SkillRegistry from harness.skills
    harness_coordinator: Optional[Any] = None     # CoordinatorManager from harness.coordinator

    # Legacy managers (for backward compatibility)
    memory_manager: Optional[Any] = None  # MemoryManager (deprecated)
    context_builder: Optional[Any] = None  # ContextBuilder (deprecated)

    # Models (lazy-loaded)
    llm_analyzer: Optional[Any] = None  # LLMVerilogAnalyzer (lazy-loaded)
    logicrt_inferencer: Optional[Any] = None  # LogicRTInferencer (lazy-loaded)

    # Console and UI
    console: Optional[Console] = None
    session_manager: Optional[PromptSession] = None

    # Circuit context
    current_aig_filename: Optional[str] = None
    last_verilog_code: Optional[str] = None
    last_analysis_report: Optional[str] = None

    # Configuration
    inference_timeout: int = field(default=config.INFERENCE_TIMEOUT)
    max_memory_rounds: int = field(default=config.MAX_MEMORY_ROUNDS)

    # Statistics
    aig_count: int = field(default=0)
    chat_turns: int = field(default=0)

    def __post_init__(self):
        """Initialize managers and console"""
        if self.console is None:
            self.console = create_console()

        # ━━━━━━━━━━ Initialize Harness Architecture ━━━━━━━━━━
        # Bootstrap: Global state management
        if self.harness_state_manager is None:
            self.harness_state_manager = get_state_manager()
            # Set working directory
            import asyncio
            try:
                asyncio.run(self.harness_state_manager.set_cwd(os.getcwd()))
            except RuntimeError:
                # Already in async context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.harness_state_manager.set_cwd(os.getcwd())
                    )
                    future.result()

        # Tasks: Task lifecycle management
        if self.harness_task_manager is None:
            self.harness_task_manager = get_task_manager()

        # Skills: Skill registry
        if self.harness_skill_registry is None:
            self.harness_skill_registry = get_skill_registry()

        # Coordinator: Multi-agent scheduling
        if self.harness_coordinator is None:
            self.harness_coordinator = get_coordinator_manager()
            # Start in Normal mode (can switch to Coordinator mode later)
            import asyncio
            try:
                asyncio.run(self.harness_coordinator.set_mode(CoordinatorMode.NORMAL))
            except RuntimeError:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.harness_coordinator.set_mode(CoordinatorMode.NORMAL)
                    )
                    future.result()

        # ━━━━━━━━━━ Initialize CktMem (Context Management) ━━━━━━━━━━
        # Initialize CktMem storage and context manager
        if self.storage is None:
            self.storage = Storage(config.CLI_DATABASE_PATH)

        if self.context_manager is None:
            system_prompt = config.LOGICRT_SYSTEM_PROMPT

            # Configure compression settings
            compact_config = CompactConfig(
                auto_compact_threshold=150_000,  # 150K tokens
                target_tokens=40_000,
                buffer_tokens=13_000,
            )

            self.context_manager = ContextManager(
                storage=self.storage,
                system_prompt=system_prompt,
                config=compact_config,
            )

        # Create session in database (async operation, run synchronously)
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # If there's a running loop, we need to handle this differently
            # For now, we'll use the synchronous approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.storage.create_session(
                        session_id=self.session_id,
                        project_name=os.path.basename(os.getcwd()),
                        working_dir=os.getcwd(),
                        model_choice=self.current_engine,
                    )
                )
                future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            asyncio.run(
                self.storage.create_session(
                    session_id=self.session_id,
                    project_name=os.path.basename(os.getcwd()),
                    working_dir=os.getcwd(),
                    model_choice=self.current_engine,
                )
            )

        if self.session_manager is None:
            # 极简样式定义 - 仅保留基础文本颜色
            cli_style = PromptStyle.from_dict({
                'completion-menu.completion': 'fg:#56b6c2',
                'completion-menu.completion.current': 'fg:#ffffff bold',
                'completion-menu.meta.completion': 'fg:#5c6370',
                'completion-menu.meta.completion.current': 'fg:#abb2bf',
            })

            # Key bindings: force popup completion on '/' key
            kb = KeyBindings()

            @kb.add('/')
            def _(event):
                """Insert '/' and force immediate completion popup without selecting first."""
                event.app.current_buffer.insert_text('/')
                event.app.current_buffer.start_completion(select_first=False)

            # Global slash command completer (regex-based to include '/')
            GLOBAL_COMMANDS = {
                "/reverse": "🚀 核心流：将 AIG 逆向工程为 Verilog",
                "/yosys": "🛠️ 进入 Yosys 逻辑综合与优化交互模式",
                "/abc": "🛠️ 进入 ABC 逻辑综合与验证交互模式",
                "/opensta": "⏱️ 进入 OpenSTA 静态时序分析交互模式",
                "/ai4eda": "🧰 进入 CktClaw Toolkit（AI4EDA 数据处理/转换）",
                # "/cktclaw": "🧰 进入 CktClaw Toolkit（AI4EDA 数据处理/转换）",
                "/rltf": "🔁 RLTF：PPA 反馈驱动的 ABC 优化序列搜索（workflows/rltf）",
                "/pareto-negotiate": "⚖️ Pareto 多智能体协商，博弈驱动 PPA（workflows/pareto_negotiation）",
                "/pareto": "⚖️ 同 /pareto-negotiate（别名）",
                "/chip-design-skills": "🔷 芯片设计子终端（提示符 [chip-design-skills]；.. 回主界面）",
                "/sessions": "📚 查看历史会话列表",
                "/about": "ℹ️ 查看 CktClaw 平台简介与能力矩阵",
                "/model": "🔀 切换当前分析引擎 (LogicRT / DeepSeek / Claude / OpenAI)",
                "/plugin": "🔌 管理插件 (list/install/remove)",
                "/tools": "🛠️ 列出已注册的工具",
                "/clear": "🧹 清屏并开启新的对话 Session",
                "/help": "📖 查看详细帮助文档",
                "/exit": "👋 退出 CktClaw 控制台",
            }
            # Magic: treat '/' as part of a word to trigger completion instantly
            slash_pattern = re.compile(r'(/[\w-]*)')
            # Pad commands for left-aligned pretty two-column layout
            pad_width = max(22, max(len(cmd) for cmd in GLOBAL_COMMANDS) + 2)
            formatted_words = [cmd.ljust(pad_width) for cmd in GLOBAL_COMMANDS.keys()]
            formatted_meta = {cmd.ljust(pad_width): desc for cmd, desc in GLOBAL_COMMANDS.items()}
            root_completer = WordCompleter(
                words=formatted_words,
                meta_dict=formatted_meta,
                pattern=slash_pattern,
                sentence=True,
                match_middle=False,
                ignore_case=False,
            )

            self.session_manager = PromptSession(
                history=FileHistory(config.HISTORY_FILE_PATH),
                completer=root_completer,
                multiline=False,  # 单行输入模式
                style=cli_style,
                enable_history_search=True,
                complete_while_typing=True,
                key_bindings=kb,
                mouse_support=False,  # 必须关闭，把滚动权还给系统终端
                include_default_pygments_style=False,
            )


# ━━━━━━━━━━ Command Parsing ━━━━━━━━━━
def parse_input(user_input: str) -> tuple[str, str]:
    """
    Parse user input into command type and arguments.

    Args:
        user_input: Raw user input string

    Returns:
        (command_type, args)
        - command_type: "aig" | "engine" | "clear" | "session" | "sessions" |
                       "help" | "chat" | "quit"
        - args: Remaining input string after command
    """
    user_input = user_input.strip()

    if not user_input:
        return "noop", ""

    # Slash commands
    if user_input.startswith("/"):
        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lstrip("/").lower()
        args = parts[1] if len(parts) > 1 else ""

        # Map commands to types
        command_map = {
            "reverse": "reverse",
            "model": "model",  # 新的交互式模型选择
            "engine": "engine",
            "abc": "abc",      # EDA tool: ABC
            "yosys": "yosys",  # EDA tool: Yosys
            "opensta": "opensta",  # EDA tool: OpenSTA
            "ai4eda": "ai4eda",  # CktClaw Toolkit
            "cktclaw": "ai4eda",
            "plugin": "plugin",
            "plugins": "plugin",
            "tools": "tools",
            "rltf": "rltf",
            "rltf-opt": "rltf",
            "rl-synth": "rltf",
            "pareto-negotiate": "pareto-negotiate",
            "pareto": "pareto-negotiate",
            "negotiate": "pareto-negotiate",
            "multi-agent": "pareto-negotiate",
            # Chip design domain skills（仅全称 /chip-*）
            "chip-architecture": "chip-architecture",
            "chip-rtl": "chip-rtl",
            "chip-verification": "chip-verification",
            "chip-formal": "chip-formal",
            "chip-synthesis": "chip-synthesis",
            "chip-dft": "chip-dft",
            "chip-sta": "chip-sta",
            "chip-hls": "chip-hls",
            "chip-pd": "chip-pd",
            "chip-soc": "chip-soc",
            "chip-compiler": "chip-compiler",
            "chip-firmware": "chip-firmware",
            "chip-fpga": "chip-fpga",
            "chip-infrastructure": "chip-infrastructure",
            "chip-design-skills": "chip-design-skills",
            "about": "about",
            "clear": "clear",
            "session": "session",
            "sessions": "sessions",
            "help": "help",
            "?": "help",
            "exit": "quit",
            "quit": "quit",
        }

        return command_map.get(cmd, "unknown"), args

    # Regular chat input
    return "chat", user_input


# ━━━━━━━━━━ Main CLI Class ━━━━━━━━━━
class LogicRTCLI:
    """
    Main CLI interface with REPL loop.
    Coordinates command dispatch, state management, and handler invocation.
    """

    def __init__(self):
        self.state = CLIState()
        self.running = True
        self.handlers: Dict[str, Any] = {}

    def startup(self):
        """Display welcome banner and initialization info"""
        console = self.state.console

        # ━━━━━━━━━━ Register Skills ━━━━━━━━━━
        # Register all bundled skills
        try:
            from .skills import (
                register_abc_skill,
                register_yosys_skill,
                register_reverse_skill,
                register_opensta_skill,
                register_ai4eda_skill,
                register_session_memory_skill,
                register_chip_design_skills,
            )
            # Register innovation skills
            from .skills.rltf_skill import register_rltf_skill
            from .skills.pareto_negotiation_skill import register_pareto_negotiation_skill
            from .skills.system_loop_skill import register_system_loop_skill

            import asyncio
            try:
                asyncio.run(register_abc_skill())
                asyncio.run(register_yosys_skill())
                asyncio.run(register_reverse_skill())
                asyncio.run(register_opensta_skill())
                asyncio.run(register_ai4eda_skill())
                asyncio.run(register_session_memory_skill())
                asyncio.run(register_rltf_skill())
                asyncio.run(register_pareto_negotiation_skill())
                asyncio.run(register_chip_design_skills())
                asyncio.run(register_system_loop_skill())
            except RuntimeError:
                # Already in async context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future1 = executor.submit(asyncio.run, register_abc_skill())
                    future2 = executor.submit(asyncio.run, register_yosys_skill())
                    future3 = executor.submit(asyncio.run, register_reverse_skill())
                    future4 = executor.submit(asyncio.run, register_opensta_skill())
                    future5 = executor.submit(asyncio.run, register_ai4eda_skill())
                    future6 = executor.submit(asyncio.run, register_session_memory_skill())
                    future7 = executor.submit(asyncio.run, register_rltf_skill())
                    future8 = executor.submit(asyncio.run, register_pareto_negotiation_skill())
                    future9 = executor.submit(asyncio.run, register_chip_design_skills())
                    future10 = executor.submit(asyncio.run, register_system_loop_skill())
                    future1.result()
                    future2.result()
                    future3.result()
                    future4.result()
                    future5.result()
                    future6.result()
                    future7.result()
                    future8.result()
                    future9.result()
                    future10.result()
        except Exception as e:
            console.print(f"[yellow]⚠️ 技能注册失败: {e}[/yellow]")

        # ━━━━━━━━━━ EDA Tool Detection + MCP Config ━━━━━━━━━━
        try:
            from .eda_tools.tool_detection import detect_all_tools, write_tool_manifest
            from .mcp.mcp_config import generate_mcp_configs, write_internal_mcp_config, write_claude_settings
            from .mcp.mcp_manager import MCPServerManager
            from pathlib import Path as _Path

            manifest = detect_all_tools()
            self.state._tool_manifest = manifest

            _manifest_path = _Path(__file__).parent / "tool-manifest.json"
            write_tool_manifest(manifest, _manifest_path)

            servers = generate_mcp_configs(manifest)
            _mcp_cfg = _Path(__file__).parent / "mcp" / "mcp-servers.json"
            write_internal_mcp_config(servers, _mcp_cfg)

            _claude_cfg = _Path(__file__).parent / ".claude" / "settings.json"
            write_claude_settings(servers, _claude_cfg)

            self.state._mcp_manager = MCPServerManager(_mcp_cfg)

            if config.VERBOSE:
                _found = len(manifest.found_tools())
                _mcp_n = len(servers)
                console.print(
                    f"[dim]🔍 EDA tools: {_found} found, "
                    f"{_mcp_n} MCP servers configured[/dim]"
                )
        except Exception as e:
            console.print(f"[dim]⚠️ Tool detection: {e}[/dim]")

        # ━━━━━━━━━━ Initialize v2 Architecture (Plugin + ToolRegistry + LLM Router) ━━━━━━━━━━
        try:
            from .plugins import get_plugin_manager
            from .tools import get_tool_registry
            from .tools.eda.yosys_tool import YosysTool
            from .tools.eda.opensta_tool import OpenSTATool
            from .tools.eda.abc_tool import ABCTool
            from .tools.eda.openroad_tool import OpenROADTool
            from .tools.system.bash_tool import BashTool
            from .llm import get_model_router

            # Initialize Tool Registry with built-in tools
            _registry = get_tool_registry()
            _registry.register(YosysTool(), source="builtin")
            _registry.register(OpenSTATool(), source="builtin")
            _registry.register(ABCTool(), source="builtin")
            _registry.register(OpenROADTool(), source="builtin")
            _registry.register(BashTool(), source="builtin")

            # Initialize LLM Model Router
            _router = get_model_router()
            _router.initialize()

            # Discover and load plugins
            _plugin_mgr = get_plugin_manager()
            _plugins = _plugin_mgr.discover_and_load_all()

            if config.VERBOSE:
                _n_tools = len(_registry.list_names())
                _n_plugins = len(_plugins)
                _n_providers = len(_router.available_providers)
                console.print(
                    f"[dim]🔌 v2 arch: {_n_tools} tools, "
                    f"{_n_plugins} plugins, "
                    f"{_n_providers} LLM providers ({', '.join(_router.available_providers)})[/dim]"
                )
        except Exception as e:
            if config.VERBOSE:
                console.print(f"[dim]⚠️ v2 arch init: {e}[/dim]")

        # ━━━━━━━━━━ Load Project Behavior (.cktclaw/) ━━━━━━━━━━
        try:
            from .bootstrap import WorkspaceParser, inject_project_behavior

            _ws_parser = WorkspaceParser(verbose=config.VERBOSE)

            import asyncio as _aio
            try:
                _behavior = _aio.run(_ws_parser.load_project_behavior())
            except RuntimeError:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as _pool:
                    _behavior = _pool.submit(
                        _aio.run, _ws_parser.load_project_behavior()
                    ).result()

            if _behavior.has_content:
                console.print("[dim]📂 Loading .cktclaw/ project behavior...[/dim]")
                try:
                    _aio.run(inject_project_behavior(_behavior, self.state))
                except RuntimeError:
                    with concurrent.futures.ThreadPoolExecutor() as _pool:
                        _pool.submit(
                            _aio.run,
                            inject_project_behavior(_behavior, self.state),
                        ).result()

        except Exception as e:
            if config.VERBOSE:
                console.print(f"[dim]⚠️ .cktclaw/ loader: {e}[/dim]")

        # Print banner
        console.print(config.WELCOME_BANNER, style="bold cyan")

        # Session info box
        session_short = self.state.session_id[:8]

        # 引擎名称转换
        engine_display = "LogicRT" if self.state.current_engine == "logicrt" else "DeepSeek"
        engine_color = "cyan" if self.state.current_engine == "deepseek" else "magenta"

        # 创建信息表格
        info_table = Table.grid(padding=(0, 2))
        info_table.add_column(style="dim")
        info_table.add_column(style="bold")

        info_table.add_row(
            f"{Icons.MEMORY} 会话 Session:",
            f"[bold]{session_short}[/bold]"
        )
        info_table.add_row(
            f"{Icons.ENGINE} 引擎 Engine:",
            f"[{engine_color}]{engine_display}[/{engine_color}]"
        )
        info_table.add_row(
            f"{Icons.DATABASE} 数据库 DB:",
            f"[dim]{Path(config.CLI_DATABASE_PATH).name}[/dim]"
        )

        # 添加 Harness 状态
        info_table.add_row(
            f"🏗️ 架构 Harness:",
            f"[green]已激活 Active[/green]"
        )

        # 创建面板
        info_panel = Panel(
            info_table,
            title="[bold cyan]系统信息 System Info[/bold cyan]",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
        )
        console.print(info_panel)
        console.print()

        # 使用提示（简洁版）
        console.print(
            "[bold]💡 快速开始 Quick Start:[/bold]\n"
            "  • 输入命令后按 [bold]Enter[/bold] 提交\n"
            "  • 按 [bold]Ctrl+C[/bold] 退出程序\n"
            "  • 输入 [bold cyan]/help[/bold cyan] 查看所有命令\n"
            "  • 输入 [bold cyan]/reverse <路径>[/bold cyan] 处理电路\n"
            "  • 输入 [bold cyan]/abc[/bold cyan] 或 [bold cyan]/yosys[/bold cyan] 进入交互式逻辑综合终端\n"
            "  • 输入 [bold cyan]/ai4eda[/bold cyan] 进入 CktClaw Toolkit（AI4EDA 数据处理/转换）\n"
            "  • 输入 [bold cyan]/rltf[/bold cyan] 或 [bold cyan]/pareto-negotiate[/bold cyan] 运行 workflow 技能\n"
            "  • 输入 [bold cyan]/model[/bold cyan] 选择分析引擎\n"
        )

    def repl_loop(self):
        """Main REPL loop - read, parse, dispatch, loop"""
        console = self.state.console

        while self.running:
            try:
                # 避免在上一轮耗时任务进行中误入缓冲区的内容被当作下一轮输入
                _flush_stdin_typeahead()
                # 极简提示符
                user_input = self.state.session_manager.prompt(
                    HTML('<ansicyan><b>CktClaw</b></ansicyan> <ansigray>></ansigray> ')
                )

                # Parse and dispatch
                if user_input.strip():
                    self._dispatch_input_sync(user_input)

            except KeyboardInterrupt:
                # 本地模型在子线程里跑 torch.generate 时，sys.exit 会等线程结束 → 极慢
                self.shutdown(from_interrupt=True)
                break
            except EOFError:
                self.shutdown(from_interrupt=False)
                break
            except Exception as e:
                render_error(console, str(e), error_type="internal")

    def _dispatch_input_sync(self, user_input: str):
        """
        Parse user input and dispatch to appropriate handler (synchronous wrapper).

        Args:
            user_input: Raw user input string
        """
        cmd_type, args = parse_input(user_input)

        console = self.state.console

        if cmd_type == "noop":
            return

        elif cmd_type == "reverse":
            from .handlers.reverse_handler import process_reverse
            # Run async handler - create new event loop if needed
            self._run_async_handler(process_reverse(args, self.state))

        elif cmd_type == "chat":
            # Use V3 streaming handler when cloud providers are configured,
            # fall back to V2 for local models
            from .handlers.chat_handler_v3 import process_chat_v3
            self._run_async_handler(process_chat_v3(user_input, self.state))

        elif cmd_type == "model":
            from .handlers.model_handler import select_model_interactive
            select_model_interactive(self.state)

        elif cmd_type == "engine":
            from .handlers.engine_handler import switch_engine
            switch_engine(args, self.state)

        elif cmd_type == "ai4eda":
            handle_ai4eda(args, self.state)

        elif cmd_type == "abc":
            from .handlers.abc_handler import handle_abc
            handle_abc(args, self.state)

        elif cmd_type == "yosys":
            from .handlers.yosys_handler import handle_yosys
            handle_yosys(args, self.state)

        elif cmd_type == "opensta":
            from .handlers.opensta_handler import handle_opensta
            handle_opensta(args, self.state)

        elif cmd_type == "rltf":
            from .handlers.workflow_skill_handler import process_workflow_skill
            self._run_async_handler(process_workflow_skill("rltf", args, self.state))

        elif cmd_type == "pareto-negotiate":
            from .handlers.workflow_skill_handler import process_workflow_skill
            self._run_async_handler(
                process_workflow_skill("pareto-negotiate", args, self.state)
            )

        elif cmd_type in (
            "chip-architecture", "chip-rtl", "chip-verification", "chip-formal",
            "chip-synthesis", "chip-dft", "chip-sta", "chip-hls", "chip-pd",
            "chip-soc", "chip-compiler", "chip-firmware", "chip-fpga", "chip-infrastructure",
        ):
            from .handlers.chip_design_handler import handle_chip_design
            self._run_async_handler(handle_chip_design(cmd_type, args, self.state))

        elif cmd_type == "chip-design-skills":
            from .handlers.chip_design_handler import handle_chip_design_skills
            handle_chip_design_skills(args, self.state)

        elif cmd_type == "clear":
            from .handlers.session_handler import create_new_session
            create_new_session(self.state)

        elif cmd_type == "session":
            from .handlers.session_handler import handle_session_command
            handle_session_command(args, self.state)

        elif cmd_type == "sessions":
            from .handlers.session_handler import handle_sessions_command
            handle_sessions_command(args, self.state)

        elif cmd_type == "help":
            from .handlers.help_handler import show_help
            show_help(self.state)

        elif cmd_type == "about":
            from .handlers.help_handler import show_about
            show_about(self.state)

        elif cmd_type == "plugin":
            from .handlers.plugin_handler import handle_plugin_command
            handle_plugin_command(args, self.state)

        elif cmd_type == "tools":
            from .handlers.tools_handler import handle_tools_command
            handle_tools_command(args, self.state)

        elif cmd_type == "quit":
            self.shutdown()

        elif cmd_type == "unknown":
            render_error(
                console,
                f"Unknown command: {user_input}. Type /help for available commands.",
                error_type="error",
            )

    def _run_async_handler(self, coro):
        """
        Run async handler in event loop, handling both cases:
        - No running loop: use asyncio.run()
        - Running loop (from prompt_toolkit): use new event loop in thread
        """
        try:
            # Try to get running loop
            loop = asyncio.get_running_loop()
            # If we get here, there's a running loop (from prompt_toolkit)
            # We need to run in a new thread to avoid nesting issues
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                try:
                    # Set timeout to allow quick exit on Ctrl+C
                    future.result(timeout=300)  # 5 minutes max
                except concurrent.futures.TimeoutError:
                    console = self.state.console
                    console.print("\n[yellow]⚠️ 操作超时[/yellow]")
                except KeyboardInterrupt:
                    # 无法取消已在执行的 worker；os._exit 不等待 ThreadPoolExecutor 收尾
                    try:
                        self.state.console.print(
                            "\n[dim]已中断：立即退出（未等待本地推理线程）[/dim]"
                        )
                    except Exception:
                        print(
                            "\n已中断，立即退出。",
                            file=sys.stderr,
                            flush=True,
                        )
                    os._exit(130)
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            try:
                asyncio.run(coro)
            except KeyboardInterrupt:
                os._exit(130)

    def shutdown(self, from_interrupt: bool = False):
        """Graceful shutdown. from_interrupt=True 时用 os._exit，避免等待 GPU 子线程。"""
        console = self.state.console
        try:
            console.print(f"\n[bold cyan]感谢使用 CKTCLAW！[/bold cyan]")
            console.print(
                f"[dim]会话已保存 Session saved: {self.state.session_id[:8]}[/dim]"
            )
        except Exception:
            pass
        self.running = False

        if from_interrupt:
            os._exit(130)
        sys.exit(0)


# ━━━━━━━━━━ Entry Point ━━━━━━━━━━
def main():
    """
    Main entry point for CktClaw CLI.
    Called by setup.py console_scripts entry point.
    """
    import argparse
    parser = argparse.ArgumentParser(description="CktClaw - EDA Agent CLI")
    parser.add_argument("--web", action="store_true", help="Start web dashboard (port 8741)")
    parser.add_argument("--web-port", type=int, default=8741, help="Web dashboard port")
    args = parser.parse_args()

    try:
        # Start web dashboard if requested
        if args.web:
            try:
                from .web import start_web_server
                start_web_server(port=args.web_port)
                print(f"[Web dashboard] http://localhost:{args.web_port}")
            except ImportError as e:
                print(f"[Warning] Web dashboard requires: pip install 'cktclaw[web]' ({e})")

        cli = LogicRTCLI()
        cli.startup()
        cli.repl_loop()
    except KeyboardInterrupt:
        print("\n[Interrupted]", flush=True)
        os._exit(130)
    except Exception as e:
        print(f"[FATAL ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
