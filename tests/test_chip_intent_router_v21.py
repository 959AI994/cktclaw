import asyncio
import json
from dataclasses import dataclass

from cktclaw.handlers.chip_intent_router import ChipIntentRouter, intent_to_route_dict
from cktclaw.handlers.schemas import ToolCandidate


@dataclass
class _FakeResponse:
    content: str


class _FakeProvider:
    def __init__(self, payload, *, prose=False, raises=None, delay=0.0):
        self.payload = payload
        self.awaited = False
        self.prose = prose
        self.raises = raises
        self.delay = delay

    async def chat(self, *args, **kwargs):
        self.awaited = True
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises:
            raise self.raises
        if self.prose:
            return _FakeResponse("this is not json")
        return _FakeResponse(json.dumps(self.payload))


class _FakeRouter:
    def __init__(self, provider):
        self.current_provider = provider
        self.current_name = "mock"

    def initialize(self):
        return None

    def get_provider(self, name):
        return self.current_provider if name == "mock" else None


def _patch_provider(monkeypatch, payload):
    provider = _FakeProvider(payload)
    import cktclaw.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_model_router", lambda: _FakeRouter(provider))
    return provider


def _patch_router(monkeypatch, provider):
    import cktclaw.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_model_router", lambda: _FakeRouter(provider))
    return provider


def _base_payload(**overrides):
    data = {
        "is_chip_task": True,
        "intent_type": "chip_mission",
        "task_domain": "rtl_design",
        "requested_scope": "multi_step_mission",
        "design_object": "tiny_npu",
        "action_verbs": ["design"],
        "deliverables": ["rtl", "testbench", "synthesis"],
        "route": "chip-mission",
        "confidence": 0.92,
        "rationale": "User asks to design a chip/IP with validation deliverables.",
        "alternatives": [],
        "missing_info": [],
        "needs_clarification": False,
        "acceptance_gates": ["rtl_generated", "simulation_pass", "synthesis_pass"],
        "normalized_user_goal": "design a tiny_npu",
    }
    data.update(overrides)
    return data


def test_async_llm_router_awaits_provider(monkeypatch):
    provider = _patch_provider(monkeypatch, _base_payload())
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我设计一个 tiny_npu"))
    assert provider.awaited is True
    assert intent.router_source == "llm"
    assert intent.intent_type == "chip_mission"
    assert intent.route == "chip-mission"
    assert intent.execution_allowed is False
    assert intent.fallback_reason is None


def test_invalid_alternatives_still_use_llm_route(monkeypatch):
    provider = _patch_provider(
        monkeypatch,
        _base_payload(alternatives=["chip-autodesign"]),
    )
    intent = asyncio.run(ChipIntentRouter().resolve_async("design a crc8 accelerator"))
    assert provider.awaited is True
    assert intent.router_source == "llm"
    assert intent.route == "chip-mission"
    assert intent.fallback_reason is None


def test_invalid_llm_schema_falls_back_to_rules(monkeypatch, tmp_path):
    provider = _patch_provider(monkeypatch, _base_payload(execution_allowed=True))
    monkeypatch.chdir(tmp_path)
    intent = asyncio.run(
        ChipIntentRouter().resolve_async(
            "tiny_npu 是什么？",
            {"session_id": "schema_test_session"},
        )
    )
    assert provider.awaited is True
    assert intent.router_source == "rules_fallback"
    assert intent.fallback_reason == "schema_validation_error"
    assert intent.intent_type == "chip_qa"
    assert intent.route == "chip-qa"
    assert intent.execution_allowed is False
    assert "schema_error:" in intent.rationale
    debug_root = tmp_path / "runs" / "router_debug" / "schema_test_session"
    assert debug_root.is_dir()
    latest = sorted(debug_root.iterdir())[-1]
    assert (latest / "raw_llm_output.txt").is_file()
    assert (latest / "validation_error.json").is_file()


def test_chip_qa_does_not_create_execution_route(monkeypatch):
    provider = _patch_provider(
        monkeypatch,
        _base_payload(
            intent_type="chip_qa",
            task_domain="general_chip_qa",
            requested_scope="conceptual_answer",
            route="chip-qa",
            deliverables=[],
            action_verbs=[],
        ),
    )
    intent = asyncio.run(ChipIntentRouter().resolve_async("NPU 和 CNN accelerator 有什么区别？"))
    route = intent_to_route_dict(intent, "NPU 和 CNN accelerator 有什么区别？")
    assert provider.awaited is True
    assert intent.intent_type == "chip_qa"
    assert route is None


def test_ambiguous_chip_input_becomes_clarification(monkeypatch):
    provider = _patch_provider(
        monkeypatch,
        _base_payload(
            intent_type="clarification",
            task_domain="rtl_design",
            requested_scope="unknown",
            route="clarification",
            confidence=0.70,
            deliverables=[],
            action_verbs=[],
            missing_info=["Specify whether to generate RTL, debug, simulate, or synthesize."],
            needs_clarification=True,
        ),
    )
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我处理这个 AXI"))
    assert provider.awaited is True
    assert intent.intent_type == "clarification"
    assert intent.needs_clarification is True
    assert intent_to_route_dict(intent, "帮我处理这个 AXI") is None


def test_tool_candidates_are_structured_and_proposal_only(monkeypatch):
    _patch_provider(
        monkeypatch,
        _base_payload(
            intent_type="chip_single_task",
            task_domain="synthesis",
            requested_scope="tool_execution",
            route="chip-single-task:synthesis",
            deliverables=["synthesis"],
            action_verbs=["synthesize"],
        ),
    )
    intent = asyncio.run(ChipIntentRouter().resolve_async("直接综合并覆盖我的原始 RTL"))
    assert intent.intent_type == "chip_single_task"
    assert intent.requires_confirmation is True
    assert intent.execution_allowed is False
    assert intent.destructive_actions
    assert intent.tool_candidates
    assert all(isinstance(tool, ToolCandidate) for tool in intent.tool_candidates)
    assert all(tool.permission == "proposal_only" for tool in intent.tool_candidates)


def test_unavailable_commercial_tool_is_not_hallucinated_as_available(monkeypatch):
    _patch_provider(
        monkeypatch,
        _base_payload(
            intent_type="chip_single_task",
            task_domain="physical_design",
            requested_scope="tool_execution",
            route="chip-single-task:physical_design",
            deliverables=["physical_design"],
            action_verbs=["run"],
        ),
    )
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我跑 Innovus placement"))
    innovus = [tool for tool in intent.tool_candidates if tool.name == "innovus"]
    assert innovus
    assert innovus[0].available is False
    assert "innovus" in intent.unsupported_tools


def test_no_provider_uses_rules_fallback(monkeypatch):
    import cktclaw.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_model_router", lambda: _FakeRouter(None))
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我设计一个 tiny_npu"))
    assert intent.router_source == "rules_fallback"
    assert intent.fallback_reason == "no_provider"
    assert intent.intent_type == "chip_mission"


def test_provider_exception_sets_fallback_reason(monkeypatch):
    provider = _patch_router(monkeypatch, _FakeProvider(_base_payload(), raises=RuntimeError("boom")))
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我设计一个 tiny_npu"))
    assert provider.awaited is True
    assert intent.router_source == "rules_fallback"
    assert intent.fallback_reason == "provider_exception"


def test_timeout_sets_fallback_reason(monkeypatch):
    provider = _patch_router(monkeypatch, _FakeProvider(_base_payload(), delay=0.05))
    router = ChipIntentRouter()
    original_wait_for = asyncio.wait_for

    async def _wait_for(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=0.001)

    monkeypatch.setattr(asyncio, "wait_for", _wait_for)
    intent = asyncio.run(router.resolve_async("帮我设计一个 tiny_npu"))
    assert provider.awaited is True
    assert intent.router_source == "rules_fallback"
    assert intent.fallback_reason == "timeout"


def test_invalid_json_sets_fallback_reason(monkeypatch):
    provider = _patch_router(monkeypatch, _FakeProvider(_base_payload(), prose=True))
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我设计一个 tiny_npu"))
    assert provider.awaited is True
    assert intent.router_source == "rules_fallback"
    assert intent.fallback_reason == "invalid_json"


def test_unknown_route_sets_fallback_reason(monkeypatch):
    provider = _patch_provider(monkeypatch, _base_payload(route="chip-magic"))
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我设计一个 tiny_npu"))
    assert provider.awaited is True
    assert intent.router_source == "rules_fallback"
    assert intent.fallback_reason == "unknown_route"


def test_context_provider_name_uses_named_provider(monkeypatch):
    provider = _FakeProvider(_base_payload())
    _patch_router(monkeypatch, provider)
    intent = asyncio.run(ChipIntentRouter().resolve_async("帮我设计一个 tiny_npu", {"provider_name": "mock"}))
    assert provider.awaited is True
    assert intent.router_source == "llm"


def test_artifact_query_route_has_no_execution_skill():
    from cktclaw.handlers.chip_intent_router import execution_skill_for_intent

    intent = asyncio.run(ChipIntentRouter().resolve_async("展示核心 RTL 代码"))
    assert intent.intent_type == "chip_artifact_query"
    assert intent.task_domain == "artifact_query"
    assert intent.requested_scope == "artifact_read"
    assert execution_skill_for_intent(intent) is None
    route = intent_to_route_dict(intent, "展示核心 RTL 代码")
    assert route is not None
    assert route["needs_orchestrator"] is False
