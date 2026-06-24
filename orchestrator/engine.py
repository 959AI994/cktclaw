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
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .parser import OrchestratorSpec, parse_orchestrator
from .state_machine import OrchestratorStateMachine, StageTransition
from .prompt_builder import build_stage_messages
from .design_state import DesignStateStore
from .qor_extractor import extract_qor_from_outputs, merge_qor
from .artifacts import enrich_snapshot_with_artifacts
from ..eda_tools.tool_detection import ToolManifest
from ..mcp.mcp_manager import MCPServerManager

logger = logging.getLogger(__name__)


def _task_needs_clarification(user_task: str) -> bool:
    """Return True when the orchestrator should ask for extra requirements.

    Short/vague tasks (e.g. ``/chip-rtl design a fifo``) benefit from clarification.
    Multi-line or structured tasks already pasted by the user should proceed directly.
    """
    text = (user_task or "").strip()
    if len(text) < 80:
        return True
    if text.count("\n") >= 2:
        return False
    if re.search(r"(?m)^\s*\d+[\.)．、]\s", text):
        return False
    if re.search(r"(?m)^\s*[-*•]\s", text):
        return False
    if any(k in text for k in ("要求：", "要求:", "约束：", "约束:", "设计目标")):
        return False
    return len(text) < 200


def _summarize_task(user_task: str, max_len: int = 120) -> str:
    """One-line summary for confirmation when skipping the clarify prompt."""
    first = (user_task or "").strip().splitlines()[0].strip()
    if len(first) <= max_len:
        return first
    return first[: max_len - 1] + "…"


def save_checkpoint(state: dict) -> Optional[Path]:
    """Persist orchestrator progress to ``<run_dir>/checkpoint.json``.

    No-op (returns None) when there is no active run.
    """
    try:
        from ..runtime.run_context import get_current_run
        run = get_current_run()
        if run is None:
            return None
        path = run.dir / "checkpoint.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception as e:
        logger.warning(f"save_checkpoint failed: {e}")
        return None


def load_checkpoint(run_id: str) -> Optional[dict]:
    """Load a previously saved checkpoint for *run_id*, or None if absent."""
    try:
        from ..runtime.run_context import run_dir_for
        path = run_dir_for(run_id) / "checkpoint.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"load_checkpoint failed: {e}")
        return None


def _extract_stage_result(response: str) -> Optional[dict]:
    """
    Extract the JSON status block from the LLM's response.

    Tries fenced ```json blocks, generic ``` fences, trailing inline JSON,
    and loose objects containing a status field.
    """
    if not response or not isinstance(response, str):
        return None

    # 1. Fenced ```json ... ```
    blocks = re.findall(r"```json\s*\n?(.*?)```", response, re.DOTALL | re.IGNORECASE)
    for block in reversed(blocks):
        parsed = _try_parse_status_json(block.strip())
        if parsed:
            return parsed

    # 2. Fenced ``` without language tag
    blocks = re.findall(r"```\s*\n?(.*?)```", response, re.DOTALL)
    for block in reversed(blocks):
        if "status" in block:
            parsed = _try_parse_status_json(block.strip())
            if parsed:
                return parsed

    # 3. Inline object with status field (one nesting level)
    m = re.search(
        r'\{(?:[^{}]|\{[^{}]*\})*"status"\s*:\s*"(PASS|FAIL|WARN)"(?:[^{}]|\{[^{}]*\})*\}',
        response,
        re.IGNORECASE,
    )
    if m:
        parsed = _try_parse_status_json(m.group(0))
        if parsed:
            return parsed

    # 4. Last {...} blob in the response (LLM often appends JSON at the end)
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response):
        parsed = _try_parse_status_json(m.group(0))
        if parsed:
            return parsed

    return None


def _try_parse_status_json(text: str) -> Optional[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "status" not in data:
        return None
    if isinstance(data.get("status"), str):
        data["status"] = data["status"].upper()
    return data


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
        self.design_state = DesignStateStore()
        self._resume_user_task: Optional[str] = None

    async def run(self, user_task: str, auto_confirm: bool = False) -> dict:
        """
        Execute the full orchestrator flow.

        Args:
            user_task: Natural-language task description.
            auto_confirm: Skip interactive requirement/confirm prompts (also enabled
                when stdin is not a TTY or CKTCLAW_ORCHESTRATOR_AUTO_CONFIRM=1).

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

        # ── Checkpoint resume (same orchestrator in active run dir) ──
        resumed = self._try_resume_from_checkpoint(user_task)
        if resumed:
            user_task = resumed
            console.print(
                f"[dim]↻ Resuming from checkpoint at stage "
                f"{self.state_machine.current_stage}[/dim]"
            )
            stage = self.state_machine.current_stage
        else:
            stage = None

        if not stage:
            skip_interactive = (
                auto_confirm
                or os.environ.get("CKTCLAW_ORCHESTRATOR_AUTO_CONFIRM")
                or not sys.stdin.isatty()
            )
            if skip_interactive:
                stage = self.state_machine.start()
                if not stage:
                    console.print("[yellow]No stages defined in orchestrator.[/yellow]")
                    return {"status": "empty", "stages": {}}
            else:
                try:
                    from prompt_toolkit import PromptSession
                    from prompt_toolkit.formatted_text import HTML

                    session = PromptSession()

                    if _task_needs_clarification(user_task):
                        console.print("\n[yellow]请描述您的具体需求（直接回车使用默认任务描述）:[/yellow]")
                        user_input = (await session.prompt_async(
                            HTML("<ansicyan>需求</ansicyan> ❯ "), default=""
                        )).strip()

                        if user_input:
                            user_task = user_task + "\n\n用户补充需求：" + user_input
                            console.print("[green]✓ 已添加用户需求[/green]")
                    else:
                        console.print(
                            f"\n[green]✓ 已识别完整需求[/green] "
                            f"[dim]({_summarize_task(user_task)})[/dim]"
                        )

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
            stage_idx = self.spec.stages.index(stage) + 1
            stage_total = len(self.spec.stages)
            console.print(
                f"\n[bold cyan]━━━ Stage: {stage} "
                f"({stage_idx}/{stage_total}) ━━━[/bold cyan]"
            )
            if hasattr(console, "emit_stage"):
                console.emit_stage(stage, stage_idx, stage_total)

            stage_result = await self._execute_stage(stage, user_task)

            # Guard: _execute_stage should always return a dict
            if not isinstance(stage_result, dict):
                _msg = (f"_execute_stage returned non-dict ({type(stage_result).__name__}): "
                        f"{repr(stage_result)[:200]}")
                logger.warning(_msg)
                stage_result = {"stage": stage, "status": "WARN", "qor": {},
                                "issues": [{"severity": "WARN", "description": _msg}]}

            status = stage_result.get("status", "FAIL")
            qor = stage_result.get("qor", {})
            if not isinstance(qor, dict):
                qor = {}

            status, stage_result = self._reconcile_pass_with_tool_errors(
                console, stage, status, qor, stage_result,
            )

            self._render_stage_result(console, stage, stage_result)

            recommendation = stage_result.get("recommendation")
            transition = self.state_machine.complete_stage(
                stage, status, qor, recommendation=recommendation,
            )

            # ── Shared blackboard + checkpoint ──
            orch_name = self.spec.name or display_name
            try:
                self.design_state.merge_stage_qor(orch_name, stage, qor, status)
                self.design_state.append_history(
                    agent=orch_name,
                    stage=stage,
                    decision=transition.action,
                    reason=transition.reason or status,
                    qor=qor,
                    recommendation=recommendation,
                )
                self.design_state.save()
            except Exception as e:
                logger.warning("design_state update failed: %s", e)

            self._persist_checkpoint(user_task)

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
        run_dir = None
        try:
            from ..runtime.run_context import get_current_run
            run = get_current_run()
            if run is not None:
                run_dir = run.dir
        except Exception:
            pass
        enriched = enrich_snapshot_with_artifacts(
            snapshot, task=user_task, run_dir=run_dir,
        )
        self._render_summary(console, enriched, display_name)
        return enriched

    async def _execute_stage(self, stage: str, user_task: str) -> dict:
        """Run one stage through LLM + tools and extract the result."""
        from .plan_schema import validate_stage_result

        def _validate(result: dict) -> dict:
            try:
                return validate_stage_result(result, stage)
            except Exception as _ve:
                logger.warning(f"Stage result validation error: {_ve}")
                result.setdefault("stage", stage)
                return result

        tool_prefs = self._get_tool_preferences()

        messages = build_stage_messages(
            spec=self.spec,
            state_machine=self.state_machine,
            stage=stage,
            user_task=user_task,
            skill_md=self.skill_md,
            manifest=self.manifest,
            tool_preference=tool_prefs,
            design_state_summary=self.design_state.summary_for_prompt(),
        )

        stage_tool_outputs: List[str] = []
        response = await self._call_llm(stage, messages, stage_tool_outputs=stage_tool_outputs)

        # Defensive: _call_llm must return str
        if not isinstance(response, str):
            response = str(response) if response is not None else ""

        result = _extract_stage_result(response)
        if isinstance(result, dict):
            extracted = extract_qor_from_outputs(stage_tool_outputs)
            result["qor"] = merge_qor(result.get("qor", {}), extracted)
            return _validate(result)

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
            followup_resp = await self._call_llm(stage, followup_msgs, stage_tool_outputs=stage_tool_outputs)
            if not isinstance(followup_resp, str):
                followup_resp = str(followup_resp) if followup_resp is not None else ""
            result = _extract_stage_result(followup_resp)
            if isinstance(result, dict):
                extracted = extract_qor_from_outputs(stage_tool_outputs)
                result["qor"] = merge_qor(result.get("qor", {}), extracted)
                return _validate(result)

        # Third attempt: dedicated JSON-only recovery (no tools, low temperature)
        if response.strip():
            recovered = await self._recover_json_status_block(stage, response[:2000])
            if isinstance(recovered, dict):
                extracted = extract_qor_from_outputs(stage_tool_outputs)
                recovered["qor"] = merge_qor(recovered.get("qor", {}), extracted)
                logger.info("Stage %s: recovered JSON via dedicated follow-up", stage)
                return _validate(recovered)

        # LLM produced a response but still no JSON block — flag as WARN
        if response.strip():
            return {
                "stage": stage,
                "status": "WARN",
                "qor": {},
                "issues": [{"severity": "WARN", "description": "LLM response lacks structured status block"}],
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

    async def _recover_json_status_block(self, stage: str, context_hint: str) -> Optional[dict]:
        """
        Last-resort JSON recovery: short LLM call with no tools, JSON-only instruction.
        """
        try:
            from ..llm.router import get_model_router
            from ..llm.base import ChatMessage
            from ..llm.types import MessageRole

            router = get_model_router()
            provider = router.current_provider
            if not provider:
                return None

            prompt = (
                f"The orchestrator stage '{stage}' has finished. "
                f"Based on the assistant output below, emit ONLY a JSON status block "
                f"(no other text, no markdown except the json fence):\n\n"
                f"```json\n"
                f'{{"stage": "{stage}", "status": "PASS", "qor": {{}}, '
                f'"issues": [], "recommendation": "proceed"}}\n'
                f"```\n\n"
                f"Use status PASS unless the output clearly indicates failure. "
                f"Include numeric metrics in qor when present.\n\n"
                f"Assistant output (truncated):\n{context_hint}"
            )
            msgs = [ChatMessage(role=MessageRole.USER, content=prompt)]
            text = ""
            async for chunk in provider.chat_stream(
                msgs, temperature=0.1, max_tokens=512,
            ):
                if chunk.text_delta:
                    text += chunk.text_delta
            return _extract_stage_result(text)
        except Exception as e:
            logger.warning("JSON recovery failed for stage %s: %s", stage, e)
            return None

    async def _call_llm(
        self,
        stage: str,
        messages: list[dict],
        stage_tool_outputs: Optional[List[str]] = None,
    ) -> str:
        """
        Call the LLM using the same infrastructure as chat_handler_v2.
        Returns the final text response.
        """
        from ..handlers.chat_handler_v2 import _chat_with_messages
        from ..models import LLMVerilogAnalyzer
        from .. import config as _ckt_config
        from ..harness.query.query_loop import create_query_loop
        from ..harness.query.query_types import QueryConfig, QueryStateEnum
        from ..ui import render_spinner, Icons

        cli_state = self.cli_state

        if cli_state.llm_analyzer is None:
            cli_state.llm_analyzer = LLMVerilogAnalyzer(
                codev_path=_ckt_config.CODEV_PATH,
                gpu_id=_ckt_config.CODEV_CHAT_GPU_ID,
                verbose=_ckt_config.VERBOSE,
            )

        # Tool/skill lookup goes through the unified CapabilityRegistry facade.
        # NOTE: the LLM call (llm_wrapper) below intentionally still uses the
        # v2 path (chat_handler_v2._chat_with_messages); only the tool layer is
        # unified here.
        from ..capability_registry import get_capability_registry as _get_cap_reg

        cap_registry = _get_cap_reg()
        all_entries = await cap_registry.list_all(user_invocable_only=True)

        # Skills excluded from chip-design orchestrator:
        # - chip-*: prevent recursive nesting
        # - rltf / pareto-negotiate / reverse: not yet stable enough for automated orchestration
        # - save_session_memory: not relevant to analysis stages; wastes tool budget
        _ORCHESTRATOR_EXCLUDED = {
            "rltf", "pareto-negotiate",
            "reverse", "reverse-aig", "aig-reverse",
            "save_session_memory", "session-memory",
            # Built-in tool names the LLM may hallucinate — not real skills
            "Read", "Write", "Bash", "Edit", "Glob", "Grep",
        }
        tools = [
            entry.to_openai_schema()
            for entry in all_entries
            if not entry.name.startswith("chip-") and entry.name not in _ORCHESTRATOR_EXCLUDED
        ]

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
            ctx = {"cli_state": cli_state}
            result = await cap_registry.execute(tool_name, tool_args, ctx)
            if stage_tool_outputs is not None:
                stage_tool_outputs.append(str(result))
            return result

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
        tool_counts: Dict[str, int] = {}
        with render_spinner(console, f"{Icons.CIRCUIT} Running {stage}...") as status:
            result = None
            async for partial in query_loop.run(messages):
                result = partial
                if (
                    result.state == QueryStateEnum.TOOL_EXECUTING
                    and result.current_tool_name
                ):
                    name = result.current_tool_name
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                    status.update(
                        f"[cyan]{Icons.CIRCUIT} {stage}: {name}[/cyan]"
                    )

        if tool_counts:
            summary = ", ".join(
                f"{name}×{count}" if count > 1 else name
                for name, count in tool_counts.items()
            )
            console.print(f"[dim]  tools: {summary}[/dim]")

        if result and result.final_response:
            return result.final_response
        return ""

    def _try_resume_from_checkpoint(self, user_task: str) -> Optional[str]:
        """Load checkpoint from active run dir if it matches this orchestrator."""
        try:
            from ..runtime.run_context import get_current_run
            run = get_current_run()
            if run is None:
                return None
            cp = load_checkpoint(run.run_id)
            if not cp or cp.get("orchestrator_name") != self.spec.name:
                return None
            sm_snap = cp.get("state_machine")
            if not sm_snap:
                return None
            resumed_stage = self.state_machine.restore_from_snapshot(sm_snap)
            if not resumed_stage:
                return None
            return cp.get("user_task", user_task)
        except Exception as e:
            logger.warning("checkpoint resume failed: %s", e)
            return None

    def _persist_checkpoint(self, user_task: str) -> None:
        """Save orchestrator progress after each stage."""
        payload = {
            "orchestrator_name": self.spec.name,
            "user_task": user_task,
            "state_machine": self.state_machine.get_state_snapshot(),
            "design_state_path": str(self.design_state.path),
        }
        save_checkpoint(payload)

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
            if isinstance(qor, dict):
                for k, v in qor.items():
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append(f"  - {qor}")
        if issues:
            lines.append("**Issues**:")
            for iss in issues:
                if isinstance(iss, dict):
                    sev = iss.get("severity", "?")
                    desc = iss.get("description", "")
                    lines.append(f"  - [{sev}] {desc}")
                else:
                    # LLM sometimes returns plain strings in issues list
                    lines.append(f"  - • {iss}")

        console.print(Panel(
            "\n".join(lines),
            title=f"[{color}]{stage} → {status}[/{color}]",
            border_style=color,
        ))

    def _reconcile_pass_with_tool_errors(
        self,
        console: Console,
        stage: str,
        status: str,
        qor: dict,
        stage_result: dict,
    ) -> tuple[str, dict]:
        """Downgrade LLM PASS when tool logs report errors inconsistent with pass."""
        if status.upper() != "PASS" or not qor:
            return status, stage_result
        downgraded = False
        if qor.get("yosys_error"):
            console.print(
                f"[yellow]⚠ {stage}: yosys_error={qor.get('yosys_error')} "
                f"but LLM reported PASS — downgrading to WARN[/yellow]"
            )
            downgraded = True
        verr = qor.get("verilator_lint_errors")
        if isinstance(verr, (int, float)) and verr > 0:
            console.print(
                f"[yellow]⚠ {stage}: verilator_lint_errors={verr} "
                f"but LLM reported PASS — downgrading to WARN[/yellow]"
            )
            downgraded = True
        if downgraded:
            stage_result = dict(stage_result)
            stage_result["status"] = "WARN"
            status = "WARN"
        return status, stage_result

    def _render_summary(self, console: Console, snapshot: dict, name: str) -> None:
        from .artifacts import build_completion_report

        report = build_completion_report(snapshot, skill=name, task="", display_name=name)
        artifacts = snapshot.get("artifacts") or []
        warnings = snapshot.get("warnings") or []

        stages_info = snapshot.get("stages", {})
        passed = sum(
            1 for s in stages_info.values()
            if isinstance(s, dict) and s.get("status") == "passed"
        )
        total = len(stages_info)

        body = (
            f"[bold]{name}[/bold] — {passed}/{total} stages passed\n"
            f"Final state: {snapshot.get('current_stage', 'N/A')}\n"
            f"Finished: {snapshot.get('finished', False)}"
        )
        if snapshot.get("workdir"):
            body += f"\nWorkdir: {snapshot['workdir']}"
        if snapshot.get("run_dir"):
            body += f"\nRun dir: {snapshot['run_dir']}"
        if artifacts:
            body += f"\n\n[bold]Deliverables ({len(artifacts)}):[/bold]"
            for item in artifacts[:12]:
                if isinstance(item, dict):
                    body += f"\n  • {item.get('path', '?')} ({item.get('kind', 'file')})"
                else:
                    body += f"\n  • {item}"
            if len(artifacts) > 12:
                body += f"\n  … +{len(artifacts) - 12} more"
        else:
            body += "\n\n[yellow]No deliverable files found on disk.[/yellow]"
        if warnings:
            body += "\n\n[yellow]Warnings:[/yellow]"
            for w in warnings[:5]:
                body += f"\n  ⚠ {w}"

        console.print(Panel(
            body,
            title="[cyan]Orchestrator Summary[/cyan]",
            border_style="cyan",
        ))
        console.print(Markdown(report))
