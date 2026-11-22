"""LLM-first chip intent router with deterministic fallback.

This module owns semantic routing only. It never executes tools and never
authorizes execution; it returns structured intent plus proposal candidates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schemas import (
    AgentCandidate,
    ArtifactQuery,
    ChipIntent,
    FallbackReason,
    RouteCandidate,
    SkillCandidate,
    ToolCandidate,
)

logger = logging.getLogger(__name__)


ALLOWED_ROUTES = {
    "chip-mission",
    "chip-single-task",
    "chip-single-task:simulation",
    "chip-single-task:testbench",
    "chip-single-task:synthesis",
    "chip-single-task:formal",
    "chip-single-task:sta",
    "chip-single-task:hls",
    "chip-single-task:physical_design",
    "chip-qa",
    "chip-artifact-query",
    "artifact-query",
    "normal-chat",
    "clarification",
    "unsafe-or-unsupported",
    # Compatibility aliases accepted from older prompts/rules.
    "chip-autodesign",
    "chip-rtl",
    "chip-verification",
    "chip-formal",
    "chip-synthesis",
    "chip-sta",
    "chip-hls",
    "chip-fpga",
    "chip-pd",
    "chip-compiler",
    "chip-system",
    "chip-infrastructure",
    "chip-pipeline",
    "erie-verilog-generator",
    "validated-rtl-generation",
    "testbench-generator",
}

_MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"

_CHAT_INDICATORS = re.compile(
    r"\b(hello|hi\b|help|about|weather|python|javascript|recipe|travel)\b|"
    r"(你好|天气|什么是\s*CktClaw|介绍你自己)",
    re.IGNORECASE,
)
_CHIP_OBJECT = re.compile(
    r"\b(chip|ip\b|rtl|verilog|systemverilog|hdl|module|block|tile|"
    r"accelerator|controller|interface|protocol|soc\b|npu|tiny[_\s.-]?npu|"
    r"dsp|fifo|axi|apb|ahb|uart|spi|i2c|crc|pwm|dma|arbiter|noc|mac\b|"
    r"alu|cache|systolic|attention|cnn|risc-v|riscv|fpga|hls|sta|yosys|"
    r"testbench|uvm|formal|netlist|timing|inference)\b|"
    r"(芯片|模块|控制器|加速器|接口|协议|推理|综合|仿真|形式验证|时序|网表|布局布线)",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(design|build|create|implement|generate|write|make|develop|synthesize|"
    r"verify|simulate|test|run|deploy|optimi[sz]e|integrate|port|prototype|"
    r"debug|fix|repair|lint)\b|"
    r"(设计|实现|生成|编写|构建|创建|验证|仿真|综合|部署|优化|集成|测试|运行|修复|调试|识别|跑一下)",
    re.IGNORECASE,
)
_QUESTION_ONLY = re.compile(
    r"^\s*(what\s+is|what are|explain|compare|difference|why|how does|"
    r"什么是|解释|介绍|对比|区别|为什么|原理)\b|是什么|有什么区别|区别是什么",
    re.IGNORECASE,
)
_BARE_GENERIC = frozenset({
    "rtl", "verilog", "systemverilog", "hdl", "synth", "synthesis",
    "sta", "timing", "fpga", "hls", "uvm", "testbench",
})

_DELIVERABLE_PATTERNS: list[tuple[str, str]] = [
    ("spec", r"\b(spec|requirements?)\b|规格"),
    ("architecture", r"\b(architecture|micro.?architecture|interface)\b|架构|接口"),
    ("rtl", r"\b(rtl|verilog|systemverilog|hdl)\b|RTL|代码"),
    ("testbench", r"\b(testbench|tb|simulation|simulate|regression)\b|测试平台|仿真|回归"),
    ("formal", r"\b(formal|property|assert)\b|形式验证|属性"),
    ("synthesis", r"\b(synth|synthesis|netlist|yosys)\b|综合|网表"),
    ("qor", r"\b(qor|area|timing|power)\b|面积|时序|功耗"),
    ("deploy", r"\b(deploy|fpga|bitstream|driver|runtime)\b|部署|驱动|运行"),
]

_SINGLE_TASK_PATTERNS: list[tuple[str, str, str]] = [
    ("simulation", "chip-single-task:simulation", r"\b(simulate|simulation|run.*tb|run.*testbench|vvp|iverilog)\b|仿真|跑.*testbench|跑.*测试"),
    ("testbench", "chip-single-task:testbench", r"\b(testbench|tb\b|cocotb|uvm)\b|测试平台|测试台"),
    ("formal", "chip-single-task:formal", r"\b(formal|fpv|property|assert|symbiyosys|sby\b|proof)\b|形式验证"),
    ("hls", "chip-single-task:hls", r"\b(hls|high.?level synthesis|c\+\+.*rtl)\b|高层次综合"),
    ("synthesis", "chip-single-task:synthesis", r"\b(synthesize|synth|synthesis|yosys|netlist|gate.?level|compile.*rtl)\b|综合|网表|门级"),
    ("sta", "chip-single-task:sta", r"\b(sta|timing|opensta|slack|setup|hold|wns|tns)\b|时序"),
    ("physical_design", "chip-single-task:physical_design", r"\b(physical design|floorplan|placement|routing|cts|openroad|innovus|gds|layout)\b|物理设计|布局布线"),
]

_ARTIFACT_QUERY = re.compile(
    r"(展示|查看|看一下|打开|读取|显示).{0,30}(核心\s*)?(RTL|代码|仿真结果|仿真日志|simulation\.log|report|报告)|"
    r"(刚才|上一轮|生成的).{0,30}(代码|RTL|仿真结果|仿真日志|report|报告)|"
    r"\b(show|open|display|read|view)\b.{0,40}\b(generated\s+)?(rtl|code|simulation\s+result|simulation\s+log|simulation\.log|report)\b",
    re.IGNORECASE,
)


class RouterFallbackError(Exception):
    def __init__(self, reason: FallbackReason, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


class UnknownRouteError(RouterFallbackError):
    def __init__(self, route: str) -> None:
        super().__init__("unknown_route", f"unknown route: {route}")


class LLMIntentDraft(BaseModel):
    """Strict LLM output shape. Execution/candidate fields are not accepted."""

    model_config = ConfigDict(extra="forbid")

    is_chip_task: bool
    intent_type: str
    task_domain: Optional[str] = None
    requested_scope: str = "unknown"
    design_object: Optional[str] = None
    action_verbs: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    route: str
    confidence: float = 0.0
    rationale: str = ""
    alternatives: list[RouteCandidate] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    acceptance_gates: list[str] = Field(default_factory=list)
    normalized_user_goal: str = ""


class ChipIntentRouter:
    """LLM-first router with deterministic fallback and policy boundaries."""

    def __init__(self) -> None:
        self.router_manifest = _load_yaml(_MANIFEST_DIR / "router_manifest.yaml")
        self.execution_manifest = _load_yaml(_MANIFEST_DIR / "execution_manifest.yaml")

    async def resolve_async(self, text: str, context: Optional[Dict[str, Any]] = None) -> ChipIntent:
        raw = (text or "").strip()
        if not raw:
            return self._normal_chat(raw, "empty input")

        slash = self._try_slash_route(raw)
        if slash is not None:
            return await self._finalize(slash, raw, context)

        if self._is_obvious_non_chip(raw):
            return self._normal_chat(raw, "obvious non-chip request")

        artifact_query = self._try_artifact_query(raw)
        if artifact_query is not None:
            return await self._finalize(artifact_query, raw, context)

        mode = os.environ.get("CKTCLAW_CHIP_ROUTER", "hybrid").strip().lower() or "hybrid"
        fallback_reason: Optional[FallbackReason] = None
        schema_error_detail: Optional[str] = None
        debug_raw_output: Optional[str] = None
        debug_draft_data: Optional[dict] = None
        if mode != "rules":
            try:
                draft_data, raw_llm_output = await self._resolve_by_llm(raw, context)
                debug_raw_output = raw_llm_output
                debug_draft_data = draft_data
                try:
                    intent = self._parse_validate(draft_data)
                except ValidationError as exc:
                    fallback_reason = "schema_validation_error"
                    schema_error_detail = _schema_error_summary(exc)
                    _persist_router_debug(
                        context,
                        raw,
                        fallback_reason,
                        schema_error_detail,
                        raw_llm_output=raw_llm_output,
                        draft_data=draft_data,
                        validation_error=exc.errors(),
                    )
                else:
                    intent = self._normalize_route(intent, raw)
                    intent = self._compute_confidence(intent, raw)
                    intent = await self._expand_capabilities(intent, raw, context)
                    intent = self._apply_policy_gates(intent, raw)
                    intent.execution_allowed = False
                    return intent
            except RouterFallbackError as exc:
                fallback_reason = exc.reason
                logger.debug("LLM chip intent routing fell back (%s): %s", exc.reason, exc)
            except asyncio.TimeoutError as exc:
                fallback_reason = "timeout"
                logger.debug("LLM chip intent routing timed out; using rules fallback: %s", exc)
            except json.JSONDecodeError as exc:
                fallback_reason = "invalid_json"
                schema_error_detail = str(exc)
                logger.debug("LLM chip intent routing returned invalid JSON; using rules fallback: %s", exc)
            except Exception as exc:
                fallback_reason = "provider_exception"
                logger.debug("LLM chip intent routing failed; using rules fallback: %s", exc)

        fallback = self._rules_fallback(raw)
        if fallback_reason:
            fallback.fallback_reason = fallback_reason
        if schema_error_detail:
            fallback.rationale = f"{fallback.rationale} (schema_error: {schema_error_detail})"
        if fallback_reason == "invalid_json" and debug_raw_output:
            _persist_router_debug(
                context,
                raw,
                fallback_reason,
                schema_error_detail,
                raw_llm_output=debug_raw_output,
            )
        return await self._finalize(fallback, raw, context)

    def resolve_rules(self, text: str, context: Optional[Dict[str, Any]] = None) -> ChipIntent:
        raw = (text or "").strip()
        slash = self._try_slash_route(raw)
        if slash is not None:
            slash.execution_allowed = False
            return slash
        if not raw:
            return self._normal_chat(raw, "empty input")
        if self._is_obvious_non_chip(raw):
            return self._normal_chat(raw, "obvious non-chip request")
        artifact_query = self._try_artifact_query(raw)
        if artifact_query is not None:
            artifact_query.execution_allowed = False
            return artifact_query
        intent = self._rules_fallback(raw)
        intent.execution_allowed = False
        return intent

    async def _finalize(self, intent: ChipIntent, text: str, context: Optional[Dict[str, Any]]) -> ChipIntent:
        intent = self._normalize_route(intent, text)
        if intent.confidence <= 0:
            intent = self._compute_confidence(intent, text)
        intent = await self._expand_capabilities(intent, text, context)
        intent = self._apply_policy_gates(intent, text)
        intent.execution_allowed = False
        return intent

    def _try_slash_route(self, text: str) -> Optional[ChipIntent]:
        if not text.startswith("/"):
            return None
        cmd = text.split(maxsplit=1)[0][1:]
        aliases = {
            "mission": "chip-mission",
            "auto-chip": "chip-mission",
            "chip-agent": "chip-mission",
            "autodesign": "chip-mission",
            "chip-auto": "chip-mission",
            "auto-rtl": "chip-mission",
        }
        route = aliases.get(cmd, cmd)
        if route not in ALLOWED_ROUTES and not route.startswith("chip-"):
            return None
        intent_type, domain, scope = _intent_shape_for_route(route)
        return ChipIntent(
            is_chip_task=route not in {"normal-chat"},
            intent_type=intent_type,
            task_domain=domain,
            requested_scope=scope,
            design_object=_extract_design_object(text),
            action_verbs=_extract_action_verbs(text),
            deliverables=_extract_deliverables(text),
            route=route,
            confidence=1.0,
            router_source="slash",
            rationale="explicit slash command",
            normalized_user_goal=text,
        )

    def _is_obvious_non_chip(self, text: str) -> bool:
        token = re.sub(r"[\s\W_]+", "", text.lower())
        if token in _BARE_GENERIC:
            return True
        return bool(_CHAT_INDICATORS.search(text) and not _CHIP_OBJECT.search(text))

    def _try_artifact_query(self, text: str) -> Optional[ChipIntent]:
        if not _is_artifact_query(text):
            return None
        kind = _artifact_kind_for_text(text)
        return ChipIntent(
            is_chip_task=True,
            intent_type="chip_artifact_query",
            task_domain="artifact_query",
            requested_scope="artifact_read",
            design_object=_extract_design_object(text),
            action_verbs=_extract_action_verbs(text),
            deliverables=[kind] if kind != "unknown" else ["artifact"],
            route="chip-artifact-query",
            confidence=0.94,
            router_source="rules_fallback",
            rationale="read-only request for artifacts from the latest chip mission",
            artifact_query=ArtifactQuery(kind=kind),
            normalized_user_goal=text,
        )

    async def _resolve_by_llm(self, text: str, context: Optional[Dict[str, Any]]) -> tuple[dict, str]:
        from ..llm.base import ChatMessage
        from ..llm.types import MessageRole

        provider, _provider_name = self._select_provider(context)
        if provider is None or not hasattr(provider, "chat"):
            raise RouterFallbackError("no_provider", "no LLM provider available")

        prompt = self._build_llm_prompt(text, context)
        response = await asyncio.wait_for(
            provider.chat(
                [ChatMessage(role=MessageRole.USER, content=prompt)],
                temperature=0.0,
                max_tokens=700,
            ),
            timeout=20,
        )
        content = str(getattr(response, "content", response))
        try:
            return json.loads(_json_object(content)), content
        except ValueError as exc:
            raise RouterFallbackError("invalid_json", str(exc)) from exc

    def _select_provider(self, context: Optional[Dict[str, Any]]) -> tuple[Any, str]:
        context = context or {}
        provider = context.get("provider")
        provider_name = str(context.get("provider_name") or "")
        if provider is not None:
            return provider, provider_name or getattr(provider, "provider_name", "context")
        try:
            from ..llm import get_model_router
            router = get_model_router()
            if hasattr(router, "initialize"):
                router.initialize()
            if provider_name:
                named = router.get_provider(provider_name) if hasattr(router, "get_provider") else None
                if named is not None:
                    return named, provider_name
            return getattr(router, "current_provider", None), getattr(router, "current_name", provider_name or "current")
        except Exception as exc:
            logger.debug("provider lookup failed: %s", exc)
            return None, provider_name or "none"

    def _build_llm_prompt(self, text: str, context: Optional[Dict[str, Any]]) -> str:
        manifest = yaml.safe_dump(self.router_manifest, allow_unicode=True, sort_keys=False)
        ctx = ""
        if context:
            safe_context = {k: v for k, v in context.items() if k in {"cwd", "files", "user_mode"}}
            if safe_context:
                ctx = "\nContext JSON:\n" + json.dumps(safe_context, ensure_ascii=False)
        return (
            "You are CktClaw's chip intent classifier. Return ONLY JSON. "
            "Use the Level-1 Router Manifest to classify semantic intent; do not select or execute tools. "
            "Do NOT output execution_allowed, agent_candidates, skill_candidates, tool_candidates, "
            "permission_gates, unsupported_tools, or destructive_actions.\n"
            "Allowed intent_type values: chip_mission, chip_single_task, chip_artifact_query, "
            "chip_qa, normal_chat, clarification, unsafe_or_unsupported.\n"
            "Allowed task_domain values: rtl_design, verification, simulation, synthesis, formal, "
            "sta, hls, physical_design, architecture_exploration, eda_debug, general_chip_qa, "
            "artifact_query, null.\n"
            "Allowed requested_scope values: conceptual_answer, single_step, multi_step_mission, "
            "code_modification, tool_execution, artifact_read, unknown.\n"
            "Allowed route values: chip-mission, chip-single-task, chip-single-task:simulation, "
            "chip-single-task:testbench, chip-single-task:synthesis, chip-single-task:formal, "
            "chip-single-task:sta, chip-single-task:hls, chip-single-task:physical_design, "
            "chip-artifact-query, chip-qa, normal-chat, clarification, unsafe-or-unsupported.\n"
            "Unknown chip/IP plus design/build/verify/simulate/synthesize/debug/deliverable -> chip_mission. "
            "Chip concept/explanation/comparison without execution -> chip_qa. "
            "Chip-related but unclear goal -> clarification.\n"
            f"Level-1 Router Manifest:\n{manifest}\n"
            f"{ctx}\n"
            f"User task: {text}\n"
            "Required JSON keys: is_chip_task, intent_type, task_domain, requested_scope, "
            "design_object, action_verbs, deliverables, route, confidence, rationale, "
            "alternatives, missing_info, needs_clarification, acceptance_gates, normalized_user_goal."
        )

    def _parse_validate(self, data: dict) -> ChipIntent:
        draft = LLMIntentDraft.model_validate(_sanitize_llm_draft(data))
        route = str(draft.route or "")
        if route not in ALLOWED_ROUTES:
            raise UnknownRouteError(route)
        intent = ChipIntent(
            is_chip_task=draft.is_chip_task,
            intent_type=draft.intent_type,  # type: ignore[arg-type]
            task_domain=draft.task_domain,  # type: ignore[arg-type]
            requested_scope=draft.requested_scope,  # type: ignore[arg-type]
            design_object=draft.design_object,
            action_verbs=draft.action_verbs,
            deliverables=draft.deliverables,
            route=route,
            confidence=float(draft.confidence or 0.0),
            router_source="llm",
            rationale=draft.rationale,
            alternatives=draft.alternatives,
            missing_info=draft.missing_info,
            needs_clarification=draft.needs_clarification,
            acceptance_gates=draft.acceptance_gates,
            normalized_user_goal=draft.normalized_user_goal,
            execution_allowed=False,
        )
        return intent

    def _normalize_route(self, intent: ChipIntent, text: str) -> ChipIntent:
        route = _normalize_route_id(intent.route, intent.task_domain)
        intent.route = route
        intent_type, domain, scope = _intent_shape_for_route(route)
        if route in {"chip-mission", "chip-qa", "normal-chat", "clarification", "unsafe-or-unsupported"}:
            intent.intent_type = intent_type
        elif intent.intent_type not in {"chip_mission", "chip_single_task"}:
            intent.intent_type = intent_type
        if intent.task_domain is None:
            intent.task_domain = domain
        if intent.requested_scope == "unknown":
            intent.requested_scope = scope
        if not intent.normalized_user_goal:
            intent.normalized_user_goal = text.strip()
        if intent.intent_type == "chip_qa":
            intent.is_chip_task = True
            intent.route = "chip-qa"
            intent.requested_scope = "conceptual_answer"
            intent.task_domain = intent.task_domain or "general_chip_qa"
        if intent.intent_type == "normal_chat":
            intent.is_chip_task = False
            intent.route = "normal-chat"
        if intent.intent_type == "clarification":
            intent.route = "clarification"
            intent.needs_clarification = True
        if intent.intent_type == "chip_artifact_query" or route == "chip-artifact-query":
            intent.intent_type = "chip_artifact_query"
            intent.task_domain = "artifact_query"
            intent.requested_scope = "artifact_read"
            intent.route = "chip-artifact-query"
            intent.is_chip_task = True
            if intent.artifact_query is None:
                intent.artifact_query = ArtifactQuery(kind=_artifact_kind_for_text(text))
        return intent

    def _compute_confidence(self, intent: ChipIntent, text: str) -> ChipIntent:
        schema_score = 1.0
        route_score = 1.0 if intent.route in ALLOWED_ROUTES else 0.0
        action_score = 1.0 if (intent.action_verbs or _ACTION.search(text)) else 0.0
        deliverable_score = 1.0 if (intent.deliverables or _extract_deliverables(text)) else 0.0
        llm_score = max(0.0, min(float(intent.confidence or 0.0), 1.0))
        final = (
            0.40 * llm_score
            + 0.20 * schema_score
            + 0.20 * route_score
            + 0.10 * action_score
            + 0.10 * deliverable_score
        )
        if intent.router_source == "slash":
            final = 1.0
        if intent.router_source == "rules_fallback" and intent.confidence > 0:
            final = max(final, min(intent.confidence, 0.92))
        intent.confidence = round(final, 3)
        return intent

    async def _expand_capabilities(
        self,
        intent: ChipIntent,
        text: str,
        context: Optional[Dict[str, Any]],
    ) -> ChipIntent:
        if intent.intent_type == "chip_artifact_query":
            intent.agent_candidates = []
            intent.skill_candidates = []
            intent.tool_candidates = []
            intent.unsupported_tools = []
            return intent
        key = _execution_manifest_key(intent)
        entry = (self.execution_manifest.get("routes") or {}).get(key) or {}
        agents = entry.get("agents") or []
        skills = entry.get("skills") or []
        tools = entry.get("tools") or []
        intent.agent_candidates = [
            AgentCandidate(name=str(a.get("name")), reason=str(a.get("reason", "")), available=True)
            for a in agents
            if a.get("name")
        ]
        intent.skill_candidates = [
            SkillCandidate(name=str(s.get("name")), reason=str(s.get("reason", "")), available=True)
            for s in skills
            if s.get("name")
        ]
        tool_candidates: list[ToolCandidate] = []
        unsupported: list[str] = []
        for tool in tools:
            name = str(tool.get("name") or "")
            if not name:
                continue
            available = await _tool_available(name, context)
            unsupported_reason = None if available else "not found in PATH or capability registry"
            if not available:
                unsupported.append(name)
            tool_candidates.append(
                ToolCandidate(
                    name=name,
                    reason=str(tool.get("reason", "")),
                    available=available,
                    unsupported_reason=unsupported_reason,
                    requires_confirmation=_looks_destructive(text),
                    destructive=_looks_destructive(text),
                )
            )

        requested_commercial = _requested_unavailable_commercial_tool(text)
        if requested_commercial and requested_commercial not in {t.name for t in tool_candidates}:
            unsupported.append(requested_commercial)
            tool_candidates.append(
                ToolCandidate(
                    name=requested_commercial,
                    reason="User requested this tool, but it is not in the active route manifest.",
                    available=False,
                    unsupported_reason="not declared for this route manifest",
                    requires_confirmation=True,
                    destructive=True,
                )
            )
        intent.tool_candidates = tool_candidates
        intent.unsupported_tools = sorted(set(intent.unsupported_tools + unsupported))
        return intent

    def _apply_policy_gates(self, intent: ChipIntent, text: str) -> ChipIntent:
        if _looks_destructive(text):
            intent.requires_confirmation = True
            if "destructive_action_confirmation" not in intent.permission_gates:
                intent.permission_gates.append("destructive_action_confirmation")
            if "overwrite_or_modify_original_rtl" not in intent.destructive_actions:
                intent.destructive_actions.append("overwrite_or_modify_original_rtl")
        if intent.unsupported_tools and "unsupported_tool_handoff" not in intent.permission_gates:
            intent.permission_gates.append("unsupported_tool_handoff")
        if intent.intent_type in {"chip_mission", "chip_single_task"} and 0.55 <= intent.confidence < 0.80:
            intent.needs_clarification = True
            if "low_confidence_confirmation" not in intent.permission_gates:
                intent.permission_gates.append("low_confidence_confirmation")
        if intent.confidence < 0.55:
            if _CHIP_OBJECT.search(text) or _ACTION.search(text):
                intent.intent_type = "clarification"
                intent.route = "clarification"
                intent.needs_clarification = True
                intent.is_chip_task = True
                if not intent.missing_info:
                    intent.missing_info = ["Specify whether you want RTL generation, verification, synthesis, debug, or explanation."]
            else:
                intent.intent_type = "normal_chat"
                intent.route = "normal-chat"
                intent.is_chip_task = False
        if intent.intent_type == "clarification" and not intent.missing_info:
            intent.missing_info = ["Please specify the chip task goal and desired deliverable."]
        intent.execution_allowed = False
        return intent

    def _rules_fallback(self, text: str) -> ChipIntent:
        text = text.strip()
        has_chip = bool(_CHIP_OBJECT.search(text))
        has_action = bool(_ACTION.search(text))
        deliverables = _extract_deliverables(text)
        actions = _extract_action_verbs(text)
        design_object = _extract_design_object(text)

        artifact_query = self._try_artifact_query(text)
        if artifact_query is not None:
            return artifact_query

        if re.search(r"(工具检测|工具.*可用|tool.*detect|available.*tools|check.*tools)", text, re.IGNORECASE):
            return _compat_single("chip-infrastructure", "eda_debug", text, design_object, actions, deliverables, "tool/infrastructure detection request")

        if re.search(r"(fix_requests?|design_state|cross-domain|pipeline orchestration|pipeline.*orchestrat|闭环|跨域)", text, re.IGNORECASE):
            return _compat_single("chip-pipeline", "eda_debug", text, design_object, actions, deliverables, "cross-domain pipeline/fix_request orchestration request")

        if _is_bare_keyword(text):
            return self._normal_chat(text, "bare EDA keyword")

        if has_chip and _QUESTION_ONLY.search(text) and not _has_build_or_execution_action(text):
            return ChipIntent(
                is_chip_task=True,
                intent_type="chip_qa",
                task_domain="general_chip_qa",
                requested_scope="conceptual_answer",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables,
                route="chip-qa",
                confidence=0.86,
                router_source="rules_fallback",
                rationale="chip concept/explanation request",
                normalized_user_goal=text,
            )

        if re.search(r"(规格|spec).{0,20}(plan|计划).{0,40}(RTL|仿真|综合|QoR|交付)|RTL.{0,20}仿真.{0,20}综合.{0,20}QoR", text, re.IGNORECASE):
            return ChipIntent(
                is_chip_task=True,
                intent_type="chip_mission",
                task_domain="rtl_design",
                requested_scope="multi_step_mission",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables or ["spec", "plan", "rtl", "simulation", "synthesis", "qor"],
                route="chip-autodesign",
                confidence=0.90,
                router_source="rules_fallback",
                rationale="explicit autodesign flow",
                acceptance_gates=["spec", "rtl_generated", "simulation_pass", "synthesis_pass", "qor_report"],
                normalized_user_goal=text,
            )

        if _is_validated_rtl_generation_request(text):
            return ChipIntent(
                is_chip_task=True,
                intent_type="chip_mission",
                task_domain="rtl_design",
                requested_scope="multi_step_mission",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables or ["rtl", "testbench", "simulation", "synthesis", "repair", "hard_gate_report"],
                route="chip-mission",
                confidence=0.92,
                router_source="rules_fallback",
                rationale="validated RTL generation with simulation, synthesis, repair loop, and hard gate report",
                acceptance_gates=[
                    "rtl_generated",
                    "tb_generated",
                    "simulation_pass",
                    "synthesis_pass",
                    "hard_gate_report",
                ],
                normalized_user_goal=text,
            )

        # Existing RTL/testbench compatibility routes keep their historical
        # priority over generic mission/single-step decisions.
        if re.search(r"\b(verilog|rtl|systemverilog|hdl).{0,60}\b(testbench|tb|self.?checking)\b|\b(testbench|tb|self.?checking).{0,60}\b(verilog|rtl|systemverilog|hdl)\b", text, re.IGNORECASE):
            return _compat_single("erie-verilog-generator", "verification", text, design_object, actions, deliverables, "RTL plus self-checking testbench request")
        if re.search(r"\b(build|create|write).{0,30}(uvm|testbench|tb\b)|功能验证", text, re.IGNORECASE):
            return _compat_single("chip-verification", "verification", text, design_object, actions, deliverables, "bounded verification/testbench request")
        if re.search(r"\b(generate.*testbench|tb.*gen|testbench.*gen|testbench.*creat)\b|生成.*testbench|测试台生成|生成.*测试台|tb.*生成", text, re.IGNORECASE):
            return _compat_single("testbench-generator", "verification", text, design_object, actions, deliverables, "testbench generator request")
        if has_chip and _is_multi_stage_design_request(text):
            return ChipIntent(
                is_chip_task=True,
                intent_type="chip_mission",
                task_domain="rtl_design",
                requested_scope="multi_step_mission",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables or ["spec", "architecture", "rtl", "testbench", "synthesis", "qor"],
                route="chip-mission",
                confidence=0.88,
                router_source="rules_fallback",
                rationale="new chip/IP design request with multiple requested stages",
                acceptance_gates=["spec", "rtl_generated", "simulation_pass", "synthesis_pass", "signoff_report"],
                normalized_user_goal=text,
            )
        if re.search(r"\b(write|generate|create|design|implement)\b.{0,35}\b(rtl|verilog|systemverilog|hdl)\b.{0,60}\b(module|block|multiplier|receiver|fifo|axi|adder|code|register)\b|\b(write|generate|create)\b.{0,20}\b(systemverilog|verilog|rtl|hdl)\b.{0,60}\bcode\b|\b(design|implement)\b.{0,50}\b(verilog|rtl|systemverilog|hdl)\b|\b(rtl|verilog)\b.{0,20}\blint\b|编写.{0,40}模块", text, re.IGNORECASE):
            return _compat_single("chip-rtl", "rtl_design", text, design_object, actions, deliverables, "single RTL implementation request")

        if has_chip and _is_new_design_mission_request(text):
            return ChipIntent(
                is_chip_task=True,
                intent_type="chip_mission",
                task_domain="rtl_design",
                requested_scope="multi_step_mission",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables or ["spec", "architecture", "rtl", "testbench", "synthesis", "qor"],
                route="chip-mission",
                confidence=0.88,
                router_source="rules_fallback",
                rationale="new chip/IP design request with action or deliverable",
                acceptance_gates=["spec", "rtl_generated", "simulation_pass", "synthesis_pass", "signoff_report"],
                normalized_user_goal=text,
            )

        for domain, route, pattern in _SINGLE_TASK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE) and _is_single_step_request(text):
                normalized_domain = "verification" if domain == "testbench" else domain
                return ChipIntent(
                    is_chip_task=True,
                    intent_type="chip_single_task",
                    task_domain=normalized_domain,  # type: ignore[arg-type]
                    requested_scope="single_step",
                    design_object=design_object,
                    action_verbs=actions,
                    deliverables=deliverables or [domain],
                    route=route,
                    confidence=0.88,
                    router_source="rules_fallback",
                    rationale=f"deterministic single-step {domain} route",
                    acceptance_gates=[f"{domain}_proposal"],
                    normalized_user_goal=text,
                )

        if has_chip and has_action and (_has_build_or_execution_action(text) or deliverables):
            return ChipIntent(
                is_chip_task=True,
                intent_type="chip_mission",
                task_domain="rtl_design",
                requested_scope="multi_step_mission",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables or ["spec", "architecture", "rtl", "testbench", "synthesis", "qor"],
                route="chip-mission",
                confidence=0.86,
                router_source="rules_fallback",
                rationale="chip design/build task with action or deliverable",
                acceptance_gates=["spec", "rtl_generated", "simulation_pass", "synthesis_pass", "signoff_report"],
                normalized_user_goal=text,
            )

        if has_chip or has_action:
            return ChipIntent(
                is_chip_task=True,
                intent_type="clarification",
                task_domain="rtl_design" if has_chip else None,
                requested_scope="unknown",
                design_object=design_object,
                action_verbs=actions,
                deliverables=deliverables,
                route="clarification",
                confidence=0.60,
                router_source="rules_fallback",
                rationale="chip-related request lacks a concrete goal",
                missing_info=["Specify whether you want RTL generation, verification, synthesis, debug, or explanation."],
                needs_clarification=True,
                normalized_user_goal=text,
            )

        return self._normal_chat(text, "no chip object/action signal")

    def _normal_chat(self, text: str, rationale: str) -> ChipIntent:
        return ChipIntent(
            is_chip_task=False,
            intent_type="normal_chat",
            task_domain=None,
            requested_scope="unknown",
            route="normal-chat",
            confidence=0.0,
            router_source="rules_fallback",
            rationale=rationale,
            normalized_user_goal=text,
            execution_allowed=False,
        )


def get_chip_intent_router() -> ChipIntentRouter:
    global _ROUTER
    try:
        return _ROUTER
    except NameError:
        _ROUTER = ChipIntentRouter()
        return _ROUTER


async def resolve_chip_intent_async(text: str, context: Optional[Dict[str, Any]] = None) -> ChipIntent:
    return await get_chip_intent_router().resolve_async(text, context)


def resolve_chip_intent_rules(text: str, context: Optional[Dict[str, Any]] = None) -> ChipIntent:
    return get_chip_intent_router().resolve_rules(text, context)


def build_chip_router_context(
    *,
    cli_state: Any = None,
    provider_name: Optional[str] = None,
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build provider/session context for ChipIntentRouter callers."""
    ctx: Dict[str, Any] = dict(extra or {})
    try:
        from ..llm import get_model_router
        router = get_model_router()
        if hasattr(router, "initialize"):
            router.initialize()
        name = provider_name or router.current_name
        provider = router.get_provider(name) if name and hasattr(router, "get_provider") else getattr(router, "current_provider", None)
        if provider is None:
            provider = getattr(router, "current_provider", None)
            name = getattr(router, "current_name", name)
        ctx.setdefault("provider", provider)
        ctx.setdefault("provider_name", name or "none")
    except Exception:
        ctx.setdefault("provider", None)
        ctx.setdefault("provider_name", provider_name or "none")
    if session_id or getattr(cli_state, "session_id", None):
        ctx.setdefault("session_id", session_id or getattr(cli_state, "session_id"))
    if cwd:
        ctx.setdefault("cwd", cwd)
    else:
        ctx.setdefault("cwd", str(Path.cwd()))
    if cli_state is not None:
        ctx.setdefault("cli_state", cli_state)
    current_engine = getattr(cli_state, "current_engine", None) if cli_state is not None else None
    if current_engine:
        ctx.setdefault("current_engine", current_engine)
    return ctx


def intent_to_route_dict(intent: ChipIntent, task: str) -> Optional[Dict[str, Any]]:
    if intent.intent_type == "chip_artifact_query":
        return {
            "skill_id": None,
            "confidence": intent.confidence,
            "score": max(1, int(round(intent.confidence * 3))),
            "needs_orchestrator": False,
            "task": task.strip(),
            "rationale": intent.rationale,
            "route_rationale": intent.rationale,
            "intent": intent.to_dict(),
            "intent_type": intent.intent_type,
            "router_source": intent.router_source,
            "fallback_reason": intent.fallback_reason,
            "route": intent.route,
            "requires_confirmation": intent.requires_confirmation,
            "permission_gates": intent.permission_gates,
            "unsupported_tools": intent.unsupported_tools,
            "destructive_actions": intent.destructive_actions,
        }
    if intent.intent_type not in {"chip_mission", "chip_single_task"}:
        return None
    skill_id = execution_skill_for_intent(intent)
    if not skill_id:
        return None
    return {
        "skill_id": skill_id,
        "confidence": intent.confidence,
        "score": max(1, int(round(intent.confidence * 3))),
        "needs_orchestrator": intent.intent_type == "chip_mission" or skill_id.startswith("chip-"),
        "task": task.strip(),
        "rationale": intent.rationale,
        "route_rationale": intent.rationale,
        "intent": intent.to_dict(),
        "intent_type": intent.intent_type,
        "router_source": intent.router_source,
        "fallback_reason": intent.fallback_reason,
        "route": intent.route,
        "requires_confirmation": intent.requires_confirmation,
        "permission_gates": intent.permission_gates,
        "unsupported_tools": intent.unsupported_tools,
        "destructive_actions": intent.destructive_actions,
    }


def execution_skill_for_intent(intent: ChipIntent) -> Optional[str]:
    if intent.intent_type == "chip_artifact_query":
        return None
    route = intent.route
    domain = intent.task_domain
    mapping = {
        "chip-single-task:simulation": "chip-verification",
        "chip-single-task:testbench": "testbench-generator",
        "chip-single-task:synthesis": "chip-synthesis",
        "chip-single-task:formal": "chip-formal",
        "chip-single-task:sta": "chip-sta",
        "chip-single-task:hls": "chip-hls",
        "chip-single-task:physical_design": "chip-pd",
        "chip-autodesign": "chip-autodesign",
        "chip-verification": "chip-verification",
        "chip-formal": "chip-formal",
        "chip-synthesis": "chip-synthesis",
        "chip-sta": "chip-sta",
        "chip-hls": "chip-hls",
        "chip-pd": "chip-pd",
        "chip-rtl": "chip-rtl",
        "chip-infrastructure": "chip-infrastructure",
        "chip-pipeline": "chip-pipeline",
        "erie-verilog-generator": "erie-verilog-generator",
        "validated-rtl-generation": "erie-verilog-generator",
        "testbench-generator": "testbench-generator",
    }
    if route in mapping:
        return mapping[route]
    if intent.intent_type == "chip_mission":
        return "chip-mission"
    domain_map = {
        "simulation": "chip-verification",
        "verification": "chip-verification",
        "synthesis": "chip-synthesis",
        "formal": "chip-formal",
        "sta": "chip-sta",
        "hls": "chip-hls",
        "physical_design": "chip-pd",
        "rtl_design": "chip-rtl",
    }
    return domain_map.get(str(domain))


def _load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.debug("failed to load manifest %s: %s", path, exc)
        return {}


def _json_object(text: str) -> str:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("missing JSON object")
    return match.group(0)


def _normalize_route_id(route: str, domain: Optional[str]) -> str:
    route = (route or "").strip()
    aliases = {
        "chip-autodesign": "chip-mission",
        "mission": "chip-mission",
        "autodesign": "chip-mission",
        "single-task": f"chip-single-task:{domain}" if domain else "chip-single-task",
        "chip-single-task": f"chip-single-task:{domain}" if domain in {
            "simulation", "synthesis", "formal", "sta", "hls", "physical_design"
        } else route,
        "artifact-query": "chip-artifact-query",
        "chip_artifact_query": "chip-artifact-query",
        "chip-verification": "chip-single-task:simulation",
        "chip-formal": "chip-single-task:formal",
        "chip-synthesis": "chip-single-task:synthesis",
        "chip-sta": "chip-single-task:sta",
        "chip-hls": "chip-single-task:hls",
        "chip-pd": "chip-single-task:physical_design",
        "qa": "chip-qa",
        "normal": "normal-chat",
        "none": "normal-chat",
        "validated_rtl_generation": "validated-rtl-generation",
        "validated-rtl-generation": "validated-rtl-generation",
    }
    return aliases.get(route, route if route in ALLOWED_ROUTES else "clarification")


def _intent_shape_for_route(route: str) -> tuple[str, Optional[str], str]:
    if route == "chip-mission":
        return "chip_mission", "rtl_design", "multi_step_mission"
    if route == "validated-rtl-generation":
        return "chip_mission", "rtl_design", "multi_step_mission"
    if route == "chip-artifact-query":
        return "chip_artifact_query", "artifact_query", "artifact_read"
    if route == "chip-qa":
        return "chip_qa", "general_chip_qa", "conceptual_answer"
    if route == "normal-chat":
        return "normal_chat", None, "unknown"
    if route == "clarification":
        return "clarification", None, "unknown"
    if route == "unsafe-or-unsupported":
        return "unsafe_or_unsupported", None, "unknown"
    if route.startswith("chip-single-task"):
        domain = route.split(":", 1)[1] if ":" in route else None
        return "chip_single_task", domain, "single_step"
    if route == "chip-pipeline":
        return "chip_single_task", "eda_debug", "single_step"
    if route in {"chip-formal", "chip-synthesis", "chip-sta", "chip-hls", "chip-pd", "chip-verification", "chip-pipeline"}:
        normalized = _normalize_route_id(route, None)
        return _intent_shape_for_route(normalized)
    return "chip_single_task", "rtl_design", "single_step"


def _execution_manifest_key(intent: ChipIntent) -> str:
    if intent.intent_type == "chip_mission":
        return "chip-mission"
    if intent.intent_type == "chip_qa":
        return "chip-qa"
    if intent.route.startswith("chip-single-task:"):
        return intent.route
    normalized = _normalize_route_id(intent.route, intent.task_domain)
    if normalized.startswith("chip-single-task:"):
        return normalized
    return intent.route


async def _tool_available(name: str, context: Optional[Dict[str, Any]]) -> bool:
    command_aliases = {
        "vvp": "vvp",
        "iverilog": "iverilog",
        "yosys": "yosys",
        "abc": "abc",
        "sby": "sby",
        "opensta": "sta",
        "openroad": "openroad",
        "innovus": "innovus",
        "vitis_hls": "vitis_hls",
    }
    if shutil.which(command_aliases.get(name, name)):
        return True
    try:
        from ..capability_registry import get_capability_registry
        cap = await get_capability_registry().get(name)
        return cap is not None
    except Exception:
        return False


def _is_bare_keyword(text: str) -> bool:
    token = re.sub(r"[\s\W_]+", "", text.lower())
    return token in _BARE_GENERIC


def _is_artifact_query(text: str) -> bool:
    return bool(_ARTIFACT_QUERY.search(text))


def _artifact_kind_for_text(text: str) -> str:
    has_sim = bool(re.search(r"\b(simulation\s+result|simulation\s+log|simulation\.log)\b|仿真结果|仿真日志", text, re.IGNORECASE))
    has_rtl = bool(re.search(r"\b(rtl|verilog|systemverilog)\b|RTL", text, re.IGNORECASE))
    has_code = bool(re.search(r"\b(code|generated\s+code)\b|代码", text, re.IGNORECASE))
    has_report = bool(re.search(r"\b(report)\b|报告", text, re.IGNORECASE))
    if sum(bool(x) for x in (has_sim, has_rtl or has_code, has_report)) > 1:
        return "unknown"
    if has_sim:
        return "simulation_log"
    if has_rtl:
        return "rtl"
    if has_code:
        return "code"
    if has_report:
        return "report"
    return "unknown"


def _extract_deliverables(text: str) -> List[str]:
    return [name for name, pattern in _DELIVERABLE_PATTERNS if re.search(pattern, text, re.IGNORECASE)]


def _extract_action_verbs(text: str) -> List[str]:
    verbs = re.findall(
        r"\b(design|build|create|implement|generate|write|make|develop|synthesize|"
        r"verify|simulate|test|run|deploy|optimi[sz]e|debug|fix|repair|lint)\b",
        text,
        re.IGNORECASE,
    )
    chinese = re.findall(r"设计|实现|生成|编写|构建|创建|验证|仿真|综合|部署|优化|测试|运行|修复|调试|识别", text)
    return sorted({v.lower() for v in verbs} | set(chinese))


def _extract_design_object(text: str) -> Optional[str]:
    patterns = [
        r"(?:design|build|create|implement|generate|write|make)\s+(?:an?\s+|the\s+)?(.{3,80}?)(?:\s+with|\s+for|\s+and|$)",
        r"(?:设计|实现|生成|构建|创建|编写)(?:一个|一款|可运行的)?(.{2,60}?)(?:并|以及|用于|可以|$)",
        r"(?:what\s+is|explain|compare)\s+(?:an?\s+|the\s+)?(.{3,80}?)(?:\?|？|$)",
        r"(?:什么是|解释|介绍|对比)(.{2,60}?)(?:\?|？|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return " ".join(match.group(1).strip(" 。,.，?？").split())
    match = re.search(r"\b([A-Za-z0-9_ -]{2,60}\s+(?:IP|block|module|controller|accelerator|tile|chip|array))\b", text, re.IGNORECASE)
    if match:
        return " ".join(match.group(1).split())
    return None


def _is_validated_rtl_generation_request(text: str) -> bool:
    """Detect full RTL+TB+sim+Yosys+repair+hard-gate delivery requests."""
    if re.search(
        r"(生成|produce|deliver).{0,80}(RTL|verilog).{0,120}(仿真|simulat|testbench|tb).{0,120}(综合|yosys|synth).{0,120}(修复|repair|fix).{0,80}(hard.?gate|报告|report)",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    if re.search(
        r"\b(rtl|verilog).{0,80}\b(testbench|tb|self.?checking).{0,120}\b(simulat|simulation).{0,120}\b(yosys|synth).{0,120}\b(repair|fix).{0,80}\b(report|hard.?gate)\b",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    markers = [
        bool(re.search(r"\b(rtl|verilog|生成\s*RTL)\b", text, re.IGNORECASE)),
        bool(re.search(r"\b(testbench|tb|self.?checking|测试台)\b", text, re.IGNORECASE)),
        bool(re.search(r"\b(simulat|仿真|iverilog|vvp)\b", text, re.IGNORECASE)),
        bool(re.search(r"\b(yosys|综合|synth)\b", text, re.IGNORECASE)),
        bool(re.search(r"\b(repair|修复|fix)\b", text, re.IGNORECASE)),
        bool(re.search(r"\b(hard.?gate|signoff|验收|报告)\b", text, re.IGNORECASE)),
    ]
    return sum(markers) >= 5


def _sanitize_llm_draft(data: dict) -> dict:
    cleaned = dict(data)
    alternatives = cleaned.get("alternatives")
    if alternatives is None or not isinstance(alternatives, list):
        cleaned["alternatives"] = []
    else:
        normalized: list[dict] = []
        for item in alternatives:
            if isinstance(item, dict):
                route = str(item.get("route") or item.get("id") or "").strip()
                if not route:
                    continue
                normalized.append({
                    "route": route,
                    "reason": str(item.get("reason") or item.get("rationale") or ""),
                    "confidence": float(item.get("confidence") or 0.0),
                })
            elif isinstance(item, str) and item.strip():
                normalized.append({"route": item.strip(), "reason": "", "confidence": 0.0})
        cleaned["alternatives"] = normalized
    try:
        cleaned["confidence"] = float(cleaned.get("confidence", 0.0))
    except (TypeError, ValueError):
        cleaned["confidence"] = 0.0
    return cleaned


def _schema_error_summary(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "schema validation failed"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = first.get("msg", "invalid value")
    if loc:
        return f"field '{loc}' {msg}"
    return str(msg)


def _persist_router_debug(
    context: Optional[Dict[str, Any]],
    user_text: str,
    reason: str,
    summary: Optional[str],
    *,
    raw_llm_output: Optional[str] = None,
    draft_data: Optional[dict] = None,
    validation_error: Optional[list] = None,
) -> None:
    context = context or {}
    session_id = str(context.get("session_id") or "unknown")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    debug_dir = Path("runs") / "router_debug" / session_id / stamp
    debug_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "reason": reason,
        "summary": summary or "",
        "user_text": user_text[:4000],
    }
    (debug_dir / "router_debug.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if raw_llm_output is not None:
        (debug_dir / "raw_llm_output.txt").write_text(raw_llm_output, encoding="utf-8")
    if draft_data is not None:
        (debug_dir / "parsed_draft.json").write_text(
            json.dumps(draft_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if validation_error is not None:
        (debug_dir / "validation_error.json").write_text(
            json.dumps(validation_error, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _has_build_or_execution_action(text: str) -> bool:
    return bool(re.search(
        r"\b(design|build|create|implement|generate|write|make|synthesize|verify|simulate|test|run|deploy|optimi[sz]e|debug|fix|repair)\b|"
        r"(设计|实现|生成|编写|构建|创建|验证|仿真|综合|部署|优化|测试|运行|修复|调试|识别)",
        text,
        re.IGNORECASE,
    ))


def _is_new_design_mission_request(text: str) -> bool:
    if re.search(r"(设计|实现|构建|创建).{0,80}(芯片|模块|控制器|加速器|接口|协议|RTL|仿真|综合|验证)", text, re.IGNORECASE):
        return True
    if re.search(
        r"\b(design|build|create|implement)\b.{0,90}\b(chip|ip\b|rtl|module|block|accelerator|controller|fifo|axi|dsp|npu|tile|crc|pwm|dma|array|core)\b",
        text,
        re.IGNORECASE,
    ):
        return True
    return bool(re.search(
        r"\b(design|build|create|implement)\b.{0,90}\b(with|and)\b.{0,90}\b(verif|simulat|synth|synthesis|qor|testbench|rtl)\b",
        text,
        re.IGNORECASE,
    ))


def _is_multi_stage_design_request(text: str) -> bool:
    return bool(re.search(
        r"\b(design|build|create|implement)\b.{0,90}\b(with|and)\b.{0,90}\b(verif|simulat|synth|synthesis|qor|deploy|testbench)\b|"
        r"(设计|实现|构建|创建).{0,80}(并|以及|完成).{0,80}(仿真|综合|验证|部署|测试)",
        text,
        re.IGNORECASE,
    ))


def _is_single_step_request(text: str) -> bool:
    return not re.search(
        r"(端到端|全流程|完整流程|从规格|spec.*plan|rtl.*(仿真|simulate).*综合|qor|signoff|交付|部署|deploy)|"
        r"\b(design|build|create|implement)\b.{0,60}\b(with|and)\b.{0,60}\b(simulat|synth|synthesis|verify|qor|deploy)\b|"
        r"(设计|实现|构建|创建).{0,80}(并|以及|完成).{0,80}(仿真|综合|验证|部署)",
        text,
        re.IGNORECASE,
    )


def _looks_destructive(text: str) -> bool:
    return bool(re.search(r"\b(overwrite|replace|delete|remove|in-place|modify original)\b|覆盖|删除|替换|原始RTL", text, re.IGNORECASE))


def _requested_unavailable_commercial_tool(text: str) -> Optional[str]:
    if re.search(r"\binnovus\b", text, re.IGNORECASE):
        return "innovus"
    return None


def _compat_single(
    route: str,
    domain: str,
    text: str,
    design_object: Optional[str],
    actions: List[str],
    deliverables: List[str],
    rationale: str,
) -> ChipIntent:
    return ChipIntent(
        is_chip_task=True,
        intent_type="chip_single_task",
        task_domain=domain,  # type: ignore[arg-type]
        requested_scope="single_step",
        design_object=design_object,
        action_verbs=actions,
        deliverables=deliverables or [domain],
        route=route,
        confidence=0.88,
        router_source="rules_fallback",
        rationale=rationale,
        normalized_user_goal=text,
    )
