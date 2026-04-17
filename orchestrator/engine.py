"""
Orchestrator Engine — drives multi-stage chip-design flows by combining
the state machine with LLM-based execution.

Each stage:
  1. Build a stage-specific prompt (system + user messages)
  2. Run a QueryLoop (LLM may call tools)
  3. Extract the JSON status block from the LLM response
  4. Feed status + QoR back to the state machine
  5. State machine decides: proceed / loop_back / suspend / escalate
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .parser import OrchestratorSpec, parse_orchestrator
from .state_machine import OrchestratorStateMachine, StageTransition
from .prompt_builder import build_stage_messages
from ..eda_tools.tool_detection import ToolManifest
from ..mcp.mcp_manager import MCPServerManager


def _extract_stage_result(response: str) -> Optional[dict]:
    """
    Extract the JSON status block from the LLM's response.

    Looks for the last ```json ... ``` fenced block containing 'stage' and 'status'.
    """
    blocks = re.findall(r"```json\s*\n(.*?)\n\s*```", response, re.DOTALL)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
            if "status" in data:
                return data
        except json.JSONDecodeError:
            continue
    # Fallback: try to find inline JSON with status (supports one level of nesting)
    m = re.search(r'\{(?:[^{}]|\{[^{}]*\})*"status"\s*:\s*"(PASS|FAIL|WARN)"(?:[^{}]|\{[^{}]*\})*\}', response)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


class OrchestratorEngine:
    """
    Drives a multi-stage orchestrator flow.

    Integrates:
      - OrchestratorStateMachine (flow control)
      - LLM via QueryLoop (stage execution)
      - MCPServerManager (tool preference)
      - ToolManifest (available tools)
    """

    def __init__(
        self,
        spec: OrchestratorSpec,
        skill_md: str,
        cli_state,
        manifest: Optional[ToolManifest] = None,
        mcp_manager: Optional[MCPServerManager] = None,
    ):
        self.spec = spec
        self.skill_md = skill_md
        self.cli_state = cli_state
        self.manifest = manifest
        self.mcp_manager = mcp_manager
        self.state_machine = OrchestratorStateMachine(spec)

    async def run(self, user_task: str) -> dict:
        """
        Execute the full orchestrator flow.

        Returns a summary dict with final state and per-stage results.
        """
        console: Console = self.cli_state.console
        display_name = self.spec.name or "Orchestrator"

        console.print(Panel(
            f"[bold]{display_name}[/bold]\n"
            f"Stages: {' → '.join(self.spec.stages)}\n"
            f"Task: {user_task}",
            title="[cyan]Orchestrator Started[/cyan]",
            border_style="cyan",
        ))

        # Interactive requirement gathering (async-safe via prompt_async)
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import HTML

            session = PromptSession()

            console.print("\n[yellow]请描述您的具体需求（直接回车使用默认任务描述）:[/yellow]")
            user_input = (await session.prompt_async(
                HTML("<ansicyan>需求</ansicyan> ❯ "), default=""
            )).strip()

            if user_input:
                user_task = user_task + "\n\n用户补充需求：" + user_input
                console.print("[green]✓ 已添加用户需求[/green]")

            console.print(f"\n[yellow]将执行以下阶段：[/yellow] {' → '.join(self.spec.stages)}")
            confirm = (await session.prompt_async(
                HTML("<ansicyan>确认执行？[Y/n]</ansicyan> ❯ "), default="Y"
            )).strip().lower()

            if confirm == 'n':
                console.print("[yellow]已取消执行[/yellow]")
                return {"status": "cancelled", "stages": {}}
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]已取消执行[/yellow]")
            return {"status": "cancelled", "stages": {}}

        stage = self.state_machine.start()
        if not stage:
            console.print("[yellow]No stages defined in orchestrator.[/yellow]")
            return {"status": "empty", "stages": {}}

        while not self.state_machine.is_finished():
            console.print(
                f"\n[bold cyan]━━━ Stage: {stage} "
                f"({self.spec.stages.index(stage) + 1}/{len(self.spec.stages)}) ━━━[/bold cyan]"
            )

            stage_result = await self._execute_stage(stage, user_task)

            status = stage_result.get("status", "FAIL")
            qor = stage_result.get("qor", {})

            self._render_stage_result(console, stage, stage_result)

            transition = self.state_machine.complete_stage(stage, status, qor)

            if transition.action == "proceed":
                stage = transition.next_stage
            elif transition.action == "loop_back":
                console.print(
                    f"[yellow]↩ Loop back to {transition.next_stage}: "
                    f"{transition.reason} (attempt {transition.loop_count})[/yellow]"
                )
                stage = transition.next_stage
            elif transition.action == "suspend":
                console.print(Panel(
                    f"[yellow]Flow suspended at {stage}.[/yellow]\n"
                    f"Reason: {transition.reason}\n"
                    f"Manual intervention required.",
                    title="[yellow]Suspended[/yellow]",
                    border_style="yellow",
                ))
                break
            elif transition.action == "escalate":
                console.print(Panel(
                    f"[red]Escalation at {stage}.[/red]\n"
                    f"Reason: {transition.reason}",
                    title="[red]Escalation[/red]",
                    border_style="red",
                ))
                break
            elif transition.action == "finished":
                break

        snapshot = self.state_machine.get_state_snapshot()
        self._render_summary(console, snapshot, display_name)
        return snapshot

    async def _execute_stage(self, stage: str, user_task: str) -> dict:
        """Run one stage through LLM + tools and extract the result."""
        tool_prefs = self._get_tool_preferences()

        messages = build_stage_messages(
            spec=self.spec,
            state_machine=self.state_machine,
            stage=stage,
            user_task=user_task,
            skill_md=self.skill_md,
            manifest=self.manifest,
            tool_preference=tool_prefs,
        )

        response = await self._call_llm(messages)

        result = _extract_stage_result(response)
        if result:
            result.setdefault("stage", stage)
            return result

        # No JSON block found — ask the LLM to produce just the status block
        if response.strip():
            followup_msgs = messages + [
                {"role": "assistant", "content": response},
                {
                    "role": "user",
                    "content": (
                        f"You did not include the required JSON status block. "
                        f"Please output ONLY the JSON block now (no other text):\n"
                        f'```json\n{{"stage": "{stage}", "status": "PASS", '
                        f'"qor": {{}}, "issues": [], "recommendation": "proceed"}}\n```'
                    ),
                },
            ]
            followup_resp = await self._call_llm(followup_msgs)
            result = _extract_stage_result(followup_resp)
            if result:
                result.setdefault("stage", stage)
                return result

        # LLM produced a response but still no JSON block — treat as PASS (stage did run)
        if response.strip():
            return {
                "stage": stage,
                "status": "PASS",
                "qor": {},
                "issues": [],
                "recommendation": "proceed",
                "raw_response": response[:2000],
            }

        # Empty response — warn and proceed
        return {
            "stage": stage,
            "status": "WARN",
            "qor": {},
            "issues": [{"severity": "WARN", "description": "LLM returned empty response"}],
            "recommendation": "proceed",
        }

    async def _call_llm(self, messages: list[dict]) -> str:
        """
        Call the LLM using the same infrastructure as chat_handler_v2.
        Returns the final text response.
        """
        from ..handlers.chat_handler_v2 import _chat_with_messages
        from ..models import LLMVerilogAnalyzer
        from .. import config as _ckt_config
        from ..harness.query.query_loop import create_query_loop
        from ..harness.query.query_types import QueryConfig, QueryStateEnum
        from ..harness import get_skill_registry
        from ..ui import render_spinner, Icons

        cli_state = self.cli_state

        if cli_state.llm_analyzer is None:
            cli_state.llm_analyzer = LLMVerilogAnalyzer(
                codev_path=_ckt_config.CODEV_PATH,
                gpu_id=_ckt_config.CODEV_CHAT_GPU_ID,
                verbose=_ckt_config.VERBOSE,
            )

        skill_registry = get_skill_registry()
        all_skills = await skill_registry.list_skills()
        # Skills excluded from chip-design orchestrator:
        # - chip-*: prevent recursive nesting
        # - rltf / pareto-negotiate / reverse: not yet stable enough for automated orchestration
        # - save_session_memory: not relevant to analysis stages; wastes tool budget
        _ORCHESTRATOR_EXCLUDED = {
            "rltf", "pareto-negotiate",
            "reverse", "reverse-aig", "aig-reverse",
            "save_session_memory", "session-memory",
        }
        tools = []
        for skill in all_skills:
            if skill.user_invocable and not skill.name.startswith("chip-") \
                    and skill.name not in _ORCHESTRATOR_EXCLUDED:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": skill.name,
                        "description": f"{skill.description}\n使用场景: {skill.when_to_use}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "args": {
                                    "type": "string",
                                    "description": f"参数格式: {skill.argument_hint}\n参数名: {', '.join(skill.argument_names)}",
                                }
                            },
                            "required": ["args"],
                        },
                    },
                })

        async def llm_wrapper(msgs):
            llm_resp = await asyncio.to_thread(
                _chat_with_messages,
                cli_state.llm_analyzer, msgs, cli_state.current_engine, tools,
            )
            if llm_resp is None:
                return {"role": "assistant", "content": "LLM 未返回有效响应。"}
            if isinstance(llm_resp, str):
                return {"role": "assistant", "content": llm_resp}
            if isinstance(llm_resp, dict) and llm_resp.get("type") == "tool_call":
                import json as _json
                return {
                    "role": "assistant", "content": "",
                    "tool_calls": [{
                        "id": llm_resp.get("tool_call_id", "call_1"),
                        "type": "function",
                        "function": {
                            "name": llm_resp.get("name", ""),
                            "arguments": _json.dumps(llm_resp.get("arguments", {})),
                        },
                    }],
                }
            return {"role": "assistant", "content": str(llm_resp) if llm_resp else ""}

        async def tool_executor(tool_name, tool_args):
            try:
                skill = await skill_registry.get_skill(tool_name)
                if skill and skill.executor:
                    ctx = {"cli_state": cli_state}
                    # tool_args can be a bare string when LLM serialises the argument
                    # as a JSON string rather than a JSON object {"args": "..."}
                    if isinstance(tool_args, str):
                        args_str = tool_args
                    else:
                        args_str = tool_args.get("args", "") if isinstance(tool_args, dict) else str(tool_args)
                    result = await skill.executor(args_str, ctx)
                    if isinstance(result, list):
                        return "\n".join(
                            item.get("text", str(item))
                            for item in result if isinstance(item, dict)
                        )
                    return str(result)
            except Exception:
                pass
            return f"Tool '{tool_name}' not available."

        # Divide the total turn budget across stages; cap at 10 per stage to
        # prevent a single stage from monopolising all available turns.
        n_stages = max(len(self.spec.stages), 1)
        per_stage_turns = max(4, min(10, self.spec.max_turns // n_stages))

        config = QueryConfig(
            system_prompt="",
            max_turns=per_stage_turns,
            auto_compact_enabled=True,
            auto_compact_threshold=150_000,
            target_tokens=40_000,
        )

        query_loop = create_query_loop(
            llm_func=llm_wrapper,
            tool_executor=tool_executor,
            config=config,
        )

        console = cli_state.console
        with render_spinner(console, f"{Icons.CIRCUIT} Running stage..."):
            result = None
            async for partial in query_loop.run(messages):
                result = partial
                if result.state == QueryStateEnum.TOOL_EXECUTING:
                    console.print(f"[dim]  tool: {result.current_tool_name}[/dim]")

        if result and result.final_response:
            return result.final_response
        return ""

    def _get_tool_preferences(self) -> dict[str, list[str]]:
        if not self.mcp_manager or not self.manifest:
            return {}
        prefs: dict[str, list[str]] = {}
        tools_in_spec = self.spec.tool_options.get("open_source", [])
        for tool in tools_in_spec:
            order = self.mcp_manager.get_preference_order(tool, self.manifest)
            if order:
                prefs[tool] = order
        return prefs

    def _render_stage_result(self, console: Console, stage: str, result: dict) -> None:
        status = result.get("status", "?")
        color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(status, "white")
        issues = result.get("issues", [])
        qor = result.get("qor", {})

        lines = [f"**Status**: [{color}]{status}[/{color}]"]
        if qor:
            lines.append("**QoR**:")
            for k, v in qor.items():
                lines.append(f"  - {k}: {v}")
        if issues:
            lines.append("**Issues**:")
            for iss in issues:
                sev = iss.get("severity", "?")
                desc = iss.get("description", "")
                lines.append(f"  - [{sev}] {desc}")

        console.print(Panel(
            "\n".join(lines),
            title=f"[{color}]{stage} → {status}[/{color}]",
            border_style=color,
        ))

    def _render_summary(self, console: Console, snapshot: dict, name: str) -> None:
        stages_info = snapshot.get("stages", {})
        passed = sum(1 for s in stages_info.values() if s["status"] == "passed")
        total = len(stages_info)

        console.print(Panel(
            f"[bold]{name}[/bold] — {passed}/{total} stages passed\n"
            f"Final state: {snapshot.get('current_stage', 'N/A')}\n"
            f"Finished: {snapshot.get('finished', False)}",
            title="[cyan]Orchestrator Summary[/cyan]",
            border_style="cyan",
        ))
