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

# Set GPU isolation BEFORE importing torch
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "2,3,4,5")

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
            # Import here to avoid loading models at startup
            from cktclaw.models import LLMVerilogAnalyzer
            system_prompt = LLMVerilogAnalyzer.LOGICRT_SYSTEM_PROMPT

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
                "/sessions": "📚 查看历史会话列表",
                "/about": "ℹ️ 查看 CktClaw 平台简介与能力矩阵",
                "/model": "🔀 切换当前分析引擎 (LogicRT / DeepSeek)",
                "/clear": "🧹 清屏并开启新的对话 Session",
                "/help": "📖 查看详细帮助文档",
                "/exit": "👋 退出 CktClaw 控制台",
            }
            # Magic: treat '/' as part of a word to trigger completion instantly
            slash_pattern = re.compile(r'(/[\w-]*)')
            # Pad commands for left-aligned pretty two-column layout
            pad_width = 12
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
            )
            # Register innovation skills
            from .skills.rltf_skill import register_rltf_skill
            from .skills.pareto_negotiation_skill import register_pareto_negotiation_skill

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
                    future1.result()
                    future2.result()
                    future3.result()
                    future4.result()
                    future5.result()
                    future6.result()
                    future7.result()
                    future8.result()
        except Exception as e:
            console.print(f"[yellow]⚠️ 技能注册失败: {e}[/yellow]")

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
            "  • 输入 [bold cyan]/model[/bold cyan] 选择分析引擎\n"
        )

    def repl_loop(self):
        """Main REPL loop - read, parse, dispatch, loop"""
        console = self.state.console

        while self.running:
            try:
                # 极简提示符
                user_input = self.state.session_manager.prompt(
                    HTML('<ansicyan><b>CktClaw</b></ansicyan> <ansigray>></ansigray> ')
                )

                # Parse and dispatch
                if user_input.strip():
                    self._dispatch_input_sync(user_input)

            except (KeyboardInterrupt, EOFError):
                # Ctrl+C 或 Ctrl+D → 退出程序
                self.shutdown()
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
            from .handlers.chat_handler_v2 import process_chat_v2
            # Run async handler - create new event loop if needed
            self._run_async_handler(process_chat_v2(user_input, self.state))

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
                future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            asyncio.run(coro)

    def shutdown(self):
        """Graceful shutdown"""
        console = self.state.console
        console.print(f"\n[bold cyan]感谢使用 CKTCLAW！[/bold cyan]")
        console.print(f"[dim]会话已保存 Session saved: {self.state.session_id[:8]}[/dim]")
        self.running = False


# ━━━━━━━━━━ Entry Point ━━━━━━━━━━
def main():
    """
    Main entry point for LogicRT CLI.
    Called by setup.py console_scripts entry point.
    """
    try:
        cli = LogicRTCLI()
        cli.startup()
        cli.repl_loop()
    except KeyboardInterrupt:
        print("\n[Interrupted]")
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
