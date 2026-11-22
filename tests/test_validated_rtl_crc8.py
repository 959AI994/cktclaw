"""Tests for validated RTL generation and CRC-8 routing/execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cktclaw.handlers.intent_router import detect_chip_design_intent, resolve_chip_intent
from cktclaw.skills.verilog_generator_skill import erie_verilog_executor
from cktclaw.workflows.validated_rtl import ValidatedRTLController
from cktclaw.workflows.validated_rtl.types import RepairState


CRC8_REQUEST = """
设计一个可综合的 CRC-8 streaming accelerator IP，模块名为 crc8_stream_accel。
功能要求：
1. 使用 CRC-8/ATM 多项式 poly=0x07。
2. 支持按字节流式输入 clk, rst_n, data_in, data_valid, data_last, crc_out, crc_valid。
3. 对字符串 "123456789"，输出 CRC 应为 8'hF4。
4. 生成 RTL、self-checking testbench、仿真脚本和 Yosys 综合脚本。
5. 如果 RTL 编译、testbench 编译、仿真或综合失败，请自动分析 log 并修复，最多 5 轮。
6. 最终报告必须包含 hard gate 表格：RTL exists、TB exists、compile PASS、simulation PASS、known vector PASS、Yosys synthesis PASS。
""".strip()


def test_crc8_route_not_erie_doc():
    intent = resolve_chip_intent(CRC8_REQUEST)
    assert intent.route == "chip-mission"
    assert intent.intent_type == "chip_mission"
    skill = detect_chip_design_intent(CRC8_REQUEST)
    assert skill == "chip-mission"


def test_erie_executor_not_skill_md(tmp_path):
    async def _run():
        return await erie_verilog_executor(
            f"{CRC8_REQUEST} --mock-provider --project-dir {tmp_path / 'erie_run'} --force",
            {"cli_state": None},
        )

    result = asyncio.run(_run())
    assert result
    item = result[0]
    assert item.get("type") != "skill_doc"
    text = item.get("text", "")
    assert "Base directory for this skill" not in text
    assert "name: erie-verilog-generator" not in text


def test_crc8_artifacts_created(tmp_path, monkeypatch):
    async def _run():
        monkeypatch.setenv("CKTCLAW_VALIDATED_RTL_MOCK", "1")
        controller = ValidatedRTLController(
            CRC8_REQUEST,
            project_dir=tmp_path / "crc8",
            use_mock_provider=True,
            force=True,
            max_repair_rounds=5,
        )
        return await controller.run()

    result = asyncio.run(_run())
    root = Path(result.project_dir)
    assert (root / "rtl").exists()
    assert (root / "tb").exists()
    assert (root / "scripts" / "run_sim.sh").is_file()
    assert (root / "scripts" / "synth_yosys.ys").is_file()
    assert (root / "reports" / "simulation.log").is_file() or result.status in {"WARN", "FAIL"}
    assert (root / "reports" / "hard_gate_report.md").is_file()
    assert (root / "reports" / "workflow_trace.json").is_file()
    trace = json.loads((root / "reports" / "workflow_trace.json").read_text(encoding="utf-8"))
    assert trace.get("rtl_llm_provider") == "mock"
    assert trace.get("rtl_llm_called") is True
    assert result.module_name == "crc8_stream_accel"


def test_hard_gate_report_gates(tmp_path):
    async def _run():
        controller = ValidatedRTLController(
            CRC8_REQUEST,
            project_dir=tmp_path / "crc8_gates",
            use_mock_provider=True,
            force=True,
        )
        return await controller.run()

    result = asyncio.run(_run())
    report = Path(result.report_path)
    text = report.read_text(encoding="utf-8")
    for gate in (
        "RTL exists",
        "TB exists",
        "compile PASS",
        "simulation PASS",
        "known vector PASS",
        "Yosys synthesis PASS",
    ):
        assert gate in text


def test_tool_missing_no_false_pass(tmp_path, monkeypatch):
    import cktclaw.workflows.validated_rtl.local_eda as local_eda

    async def _run():
        monkeypatch.setattr(local_eda.shutil, "which", lambda _name: None)
        controller = ValidatedRTLController(
            CRC8_REQUEST,
            project_dir=tmp_path / "crc8_tools",
            use_mock_provider=True,
            force=True,
        )
        return await controller.run()

    result = asyncio.run(_run())
    assert result.status != "PASS"
    statuses = {g.gate: g.status for g in result.hard_gates}
    assert statuses.get("compile PASS") == "tool_missing" or statuses.get("simulation PASS") == "tool_missing"


def test_repair_escalation():
    repair = RepairState(max_rounds=5)
    assert repair.record_failure("sim:fail") is False
    assert repair.record_failure("sim:fail") is True
    assert repair.escalated is True
    assert repair.exhausted is True


def test_schema_error_artifacts(tmp_path, monkeypatch):
    from cktclaw.handlers.chip_intent_router import ChipIntentRouter

    payload = {
        "is_chip_task": True,
        "intent_type": "chip_mission",
        "task_domain": "rtl_design",
        "requested_scope": "multi_step_mission",
        "design_object": "crc8",
        "action_verbs": ["design"],
        "deliverables": ["rtl"],
        "route": "chip-mission",
        "confidence": 0.9,
        "rationale": "test",
        "alternatives": [],
        "missing_info": [],
        "needs_clarification": False,
        "acceptance_gates": [],
        "normalized_user_goal": "design crc8",
        "execution_allowed": True,
    }

    class _Resp:
        content = json.dumps(payload)

    class _Prov:
        async def chat(self, *args, **kwargs):
            return _Resp()

    class _Router:
        current_provider = _Prov()
        current_name = "mock"

        def initialize(self):
            return None

        def get_provider(self, name):
            return self.current_provider

    import cktclaw.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_model_router", lambda: _Router())
    monkeypatch.chdir(tmp_path)
    intent = asyncio.run(
        ChipIntentRouter().resolve_async(
            "design crc8",
            {"session_id": "test_schema_session"},
        )
    )
    assert intent.fallback_reason == "schema_validation_error"
    debug_root = tmp_path / "runs" / "router_debug" / "test_schema_session"
    assert debug_root.is_dir()
    run_dirs = list(debug_root.iterdir())
    assert run_dirs
    latest = sorted(run_dirs)[-1]
    assert (latest / "raw_llm_output.txt").is_file()
    assert (latest / "validation_error.json").is_file()
    validation = json.loads((latest / "validation_error.json").read_text(encoding="utf-8"))
    assert validation


def test_adapter_loader_imports_from_absolute_path():
    from cktclaw.workflows.validated_rtl.adapter_loader import load_verilog_adapter

    result = load_verilog_adapter()
    assert result.ok, result.error
    assert result.module is not None
    assert hasattr(result.module, "run_verilog_workflow")


def test_router_sanitizes_invalid_alternatives(monkeypatch):
    from cktclaw.handlers.chip_intent_router import ChipIntentRouter, _sanitize_llm_draft

    sanitized = _sanitize_llm_draft({
        "is_chip_task": True,
        "intent_type": "chip_mission",
        "task_domain": "rtl_design",
        "requested_scope": "multi_step_mission",
        "route": "chip-mission",
        "confidence": "0.91",
        "alternatives": ["chip-autodesign", {"route": "chip-rtl", "reason": "fallback"}],
        "missing_info": [],
        "needs_clarification": False,
        "acceptance_gates": [],
        "normalized_user_goal": "design crc8",
        "rationale": "test",
    })
    assert sanitized["alternatives"][0]["route"] == "chip-autodesign"
    assert sanitized["alternatives"][1]["route"] == "chip-rtl"
    assert sanitized["confidence"] == 0.91

    payload = {
        "is_chip_task": True,
        "intent_type": "chip_mission",
        "task_domain": "rtl_design",
        "requested_scope": "multi_step_mission",
        "design_object": "crc8",
        "action_verbs": ["design"],
        "deliverables": ["rtl"],
        "route": "chip-mission",
        "confidence": 0.9,
        "rationale": "test",
        "alternatives": ["chip-autodesign"],
        "missing_info": [],
        "needs_clarification": False,
        "acceptance_gates": [],
        "normalized_user_goal": "design crc8",
    }

    class _Resp:
        content = json.dumps(payload)

    class _Prov:
        async def chat(self, *args, **kwargs):
            return _Resp()

    class _Router:
        current_provider = _Prov()
        current_name = "mock"

        def initialize(self):
            return None

        def get_provider(self, name):
            return self.current_provider

    import cktclaw.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_model_router", lambda: _Router())
    intent = asyncio.run(ChipIntentRouter().resolve_async("design crc8"))
    assert intent.router_source == "llm"
    assert intent.fallback_reason is None


def test_mission_fails_when_autodesign_import_fails(tmp_path, monkeypatch):
    from cktclaw.agents.mission_control import ChipMissionControl

    async def _fake_run(self, task, *, context=None):
        return {
            "role_id": "eda_agent",
            "status": "failed",
            "output": "## chip-autodesign\nChip AutoDesign failed: No module named 'integration.verilog_adapter'",
            "artifacts": [],
            "error": "No module named 'integration.verilog_adapter'",
            "steps": [],
        }

    monkeypatch.setattr(
        "cktclaw.agents.runners.eda_agent_runner.EDAAgentRunner.run",
        _fake_run,
    )

    async def _run():
        mission = ChipMissionControl(
            CRC8_REQUEST,
            project_dir=tmp_path / "mission_fail",
            force=True,
            max_mission_rounds=1,
            progress_quiet=True,
        )
        return await mission.run()

    result = asyncio.run(_run())
    assert result.status == "FAIL"


def test_simulation_passes_on_test_passed_string():
    from cktclaw.workflows.validated_rtl.local_eda import _simulation_passed

    output = "PASS: CRC = f4 (expected f4)\n*** TEST PASSED ***\n"
    assert _simulation_passed(0, output, True) is True


def test_bridge_normalizes_filepath_comment():
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import normalize_verilog_generator_response

    raw = """```verilog
// filepath=rtl/crc8_stream_accel.v
module crc8_stream_accel(); endmodule
```"""
    normalized = normalize_verilog_generator_response(raw)
    assert "```verilog path=rtl/crc8_stream_accel.v" in normalized


def test_mission_retries_until_pass(tmp_path, monkeypatch):
    from cktclaw.agents.mission_control import ChipMissionControl

    calls = {"count": 0}

    async def _fake_run(self, task, *, context=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "role_id": "eda_agent",
                "status": "failed",
                "output": "## chip-autodesign\n**Status:** FAIL\nChip AutoDesign failed: sim",
                "artifacts": [],
                "error": "simulation failed",
                "steps": [],
            }
        return {
            "role_id": "eda_agent",
            "status": "completed",
            "output": "## chip-autodesign\n**Status:** PASS",
            "artifacts": [],
            "error": None,
            "steps": [],
        }

    monkeypatch.setattr(
        "cktclaw.agents.runners.eda_agent_runner.EDAAgentRunner.run",
        _fake_run,
    )
    async def _fake_optimizer(self, step, phases, mission_round=1):
        from cktclaw.agents.mission_control import MissionPhaseResult
        return MissionPhaseResult(
            phase=step.phase,
            role_id=step.role_id,
            status="completed",
            output="recommend iteration",
            artifacts=[],
        )

    monkeypatch.setattr(
        "cktclaw.agents.mission_control.ChipMissionControl._run_optimizer_agent",
        _fake_optimizer,
    )
    async def _noop_repair(self, eda_phase, mission_round):
        return None

    monkeypatch.setattr(
        "cktclaw.agents.mission_control.ChipMissionControl._dispatch_mission_repair",
        _noop_repair,
    )

    async def _run():
        mission = ChipMissionControl(
            "design crc8",
            project_dir=tmp_path / "mission_retry",
            force=True,
            max_mission_rounds=3,
            progress_quiet=True,
        )
        return await mission.run()

    result = asyncio.run(_run())
    assert calls["count"] >= 2
    assert result.status == "PASS"
    assert (tmp_path / "mission_retry" / "iteration_002").is_dir()


def test_rtl_llm_cli_summary_from_workflow_trace(tmp_path):
    from cktclaw.workflows.validated_rtl.observability import format_rtl_llm_cli_summary

    trace_dir = tmp_path / "eda_validated_rtl" / "reports"
    trace_dir.mkdir(parents=True)
    trace_dir.joinpath("workflow_trace.json").write_text(
        json.dumps(
            {
                "rtl_llm_provider": "command",
                "rtl_llm_called": True,
                "rtl_llm_status": "completed",
            }
        ),
        encoding="utf-8",
    )
    summary = format_rtl_llm_cli_summary(tmp_path, overall_status="PASS")
    assert "RTL LLM: command via cktclaw_llm_bridge (called)" in summary

    fail_summary = format_rtl_llm_cli_summary(tmp_path / "missing", overall_status="FAIL")
    assert "not reached" in fail_summary

    salvage_root = tmp_path / "salvage_mission"
    salvage_trace_dir = salvage_root / "eda_validated_rtl" / "reports"
    salvage_trace_dir.mkdir(parents=True)
    salvage_trace_dir.joinpath("workflow_trace.json").write_text(
        json.dumps(
            {
                "rtl_llm_provider": "command",
                "rtl_llm_called": True,
                "rtl_llm_status": "constraint_failed: Expecting ',' delimiter",
                "workflow_error": "Expecting ',' delimiter",
                "generation_mode": "salvage",
                "execution_stack": "generator=LLM constraint=verilog-generator hard_gate=local_eda",
            }
        ),
        encoding="utf-8",
    )
    salvage_summary = format_rtl_llm_cli_summary(salvage_root, overall_status="FAIL")
    assert "constraint failed" in salvage_summary
    assert "mode=salvage" in salvage_summary


def test_cktclaw_llm_bridge_uses_chat_message(monkeypatch):
    from cktclaw.llm.base import ChatMessage
    from cktclaw.llm.types import MessageRole
    from cktclaw.workflows.validated_rtl import cktclaw_llm_bridge

    captured: dict = {}

    class _Response:
        content = "module crc8_stream_accel(); endmodule"

    class _Provider:
        async def chat(self, messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return _Response()

    class _Router:
        current_provider = _Provider()

    monkeypatch.setattr(
        "cktclaw.llm.router.get_model_router",
        lambda: _Router(),
    )

    text = asyncio.run(cktclaw_llm_bridge._generate("generate rtl"))
    assert "crc8_stream_accel" in text
    assert len(captured["messages"]) == 1
    assert isinstance(captured["messages"][0], ChatMessage)
    assert captured["messages"][0].role == MessageRole.USER


def test_normalize_verilog_generator_response_moves_path_comment():
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import normalize_verilog_generator_response

    raw = """```json
{"target": "rtl", "name": "crc8", "files": [{"path": "model/a.py"}]}
```

```python
# path=model/a.py
print("ok")
```

```json
# path=model/a.json
[]
```"""
    normalized = normalize_verilog_generator_response(raw)
    assert "```python path=model/a.py" in normalized
    assert "```json path=model/a.json" in normalized
    assert "# path=model/a.py" not in normalized.split("```python path=model/a.py", 1)[1].split("```", 1)[0]


def test_normalize_verilog_generator_response_moves_bare_path_line():
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import normalize_verilog_generator_response

    raw = """```json
{"target": "rtl", "name": "crc8", "files": [{"path": "model/a.py"}, {"path": "model/a.json"}]}
```

```python
path=model/a.py
print("ok")
```

```json
path=model/a.json
[]
```"""
    normalized = normalize_verilog_generator_response(raw)
    assert "```python path=model/a.py" in normalized
    assert "```json path=model/a.json" in normalized


def test_normalize_fixes_recorded_crc8_python_response():
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import normalize_verilog_generator_response

    for mission_id in ("35aba3ed1229", "321fd35bafd3", "ccd4fecf5cd7"):
        response_path = Path(
            f"/home/wjx/pythonproject/runs/chip_mission/{mission_id}/"
            "eda_autodesign/eda_validated_rtl/workflow/attempt-001/python/python_response.md"
        )
        if not response_path.is_file():
            continue
        normalized = normalize_verilog_generator_response(response_path.read_text(encoding="utf-8"))
        assert "```python path=model/crc8_stream_accel_model.py" in normalized
        assert "```json path=model/crc8_stream_accel_vectors.json" in normalized
        break
    else:
        return


def test_sanitize_json_fence_hex_and_comments():
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import normalize_verilog_generator_response

    raw = """```json path=model/crc8_stream_accel_vectors.json
# reference vectors
[
  {"name": "single_byte", "inputs": [{"in_data": 0x31}]}
]
```"""
    normalized = normalize_verilog_generator_response(raw)
    block = normalized.split("```json path=model/crc8_stream_accel_vectors.json", 1)[1].split("```", 1)[0]
    payload = json.loads(block.strip())
    assert payload[0]["inputs"][0]["in_data"] == 49


def test_sanitize_json_fence_passes_audit_vectors(tmp_path):
    from cktclaw.workflows.validated_rtl.adapter_loader import load_verilog_adapter
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import normalize_verilog_generator_response

    raw = """```json path=model/crc8_stream_accel_vectors.json
[
  {"name": "single_byte", "inputs": [{"in_data": 0x31}], "expected_outputs": [{"out_data": 0xF4}]}
]
```"""
    normalized = normalize_verilog_generator_response(raw)
    block = normalized.split("```json path=model/crc8_stream_accel_vectors.json", 1)[1].split("```", 1)[0]
    vectors_path = tmp_path / "crc8_stream_accel_vectors.json"
    vectors_path.write_text(block.strip() + "\n", encoding="utf-8")

    adapter = load_verilog_adapter()
    assert adapter.ok, adapter.error
    from runtime.verilog_generator.vectors import audit_vectors

    contract = audit_vectors(vectors_path)
    assert contract["case_count"] == 1


def test_inject_missing_vectors_fence_from_generated(tmp_path):
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import (
        inject_missing_manifest_fences,
        patch_workflow_python_responses,
    )

    workflow_dir = tmp_path / "workflow"
    attempt_dir = workflow_dir / "attempt-001" / "python"
    generated_dir = attempt_dir / "generated" / "model"
    generated_dir.mkdir(parents=True)
    vectors_path = generated_dir / "crc8_stream_accel_vectors.json"
    vectors_path.write_text(
        json.dumps([{"name": "known_vector_123456789", "expected_crc": 244}]),
        encoding="utf-8",
    )
    response_path = attempt_dir / "python_response.md"
    response_path.write_text(
        """```json
{"target": "python", "name": "crc8_stream_accel", "files": [
  {"path": "model/crc8_stream_accel_model.py"},
  {"path": "model/crc8_stream_accel_vectors.json"}
]}
```

```python path=model/crc8_stream_accel_model.py
print("model")
```
""",
        encoding="utf-8",
    )

    patched = patch_workflow_python_responses(workflow_dir)
    assert "model/crc8_stream_accel_vectors.json" in patched
    normalized = response_path.read_text(encoding="utf-8")
    assert "```json path=model/crc8_stream_accel_vectors.json" in normalized

    text, injected = inject_missing_manifest_fences(
        response_path.read_text(encoding="utf-8"),
        [generated_dir, attempt_dir / "generated", attempt_dir],
    )
    assert injected == []


def test_compile_failure_downgrades_to_minimal_crc8_tb(tmp_path, monkeypatch):
    from cktclaw.workflows.validated_rtl.controller import ValidatedRTLController
    from cktclaw.workflows.validated_rtl.repair_helpers import is_compile_failure

    controller = ValidatedRTLController(
        CRC8_REQUEST,
        project_dir=tmp_path / "compile_downgrade",
        use_mock_provider=True,
        force=True,
        max_repair_rounds=1,
    )
    controller._prepare_dirs()
    controller.rtl_dir.mkdir(parents=True, exist_ok=True)
    controller.tb_dir.mkdir(parents=True, exist_ok=True)
    (controller.rtl_dir / "crc8_stream_accel.v").write_text(
        "module crc8_stream_accel(input clk, input rst_n, input data_valid, input [7:0] data_in, "
        "input data_last, output reg crc_valid, output reg [7:0] crc_out); endmodule\n",
        encoding="utf-8",
    )
    bad_tb = controller.tb_dir / "crc8_stream_accel_tb.v"
    bad_tb.write_text(
        "module crc8_stream_accel_tb; task t(input [7:0] arr [0:3]); endtask endmodule\n",
        encoding="utf-8",
    )

    sim_fail = {
        "status": "FAIL",
        "issues": ["compile failed"],
        "output": "error: Subroutine ports with unpacked dimensions are not yet supported\n",
    }
    assert is_compile_failure(sim_fail) is True
    assert controller._maybe_downgrade_tb_for_compile_failure("crc8_stream_accel_tb.v") is True
    tb_text = bad_tb.read_text(encoding="utf-8")
    assert "TEST PASSED" in tb_text
    assert "task t" not in tb_text
    assert "8'hF4" in tb_text


def test_materialize_prefers_attempt_generated(tmp_path):
    from cktclaw.workflows.validated_rtl.controller import ValidatedRTLController, build_spec_from_task

    controller = ValidatedRTLController(
        CRC8_REQUEST,
        project_dir=tmp_path / "materialize_priority",
        use_mock_provider=True,
        force=True,
    )
    controller._prepare_dirs()
    low_priority = controller.workflow_dir / "salvage_extracted" / "rtl" / "crc8_stream_accel.v"
    low_priority.parent.mkdir(parents=True)
    low_priority.write_text("module crc8_stream_accel(); endmodule // salvage\n", encoding="utf-8")
    high_priority = (
        controller.workflow_dir
        / "attempt-001"
        / "rtl"
        / "generated"
        / "rtl"
        / "crc8_stream_accel.v"
    )
    high_priority.parent.mkdir(parents=True)
    high_priority.write_text(
        "module crc8_stream_accel(input clk); endmodule // generated\n",
        encoding="utf-8",
    )
    tb_path = controller.workflow_dir / "attempt-001" / "rtl" / "generated" / "tb" / "crc8_stream_accel_tb.v"
    tb_path.parent.mkdir(parents=True)
    tb_path.write_text(
        "module crc8_stream_accel_tb; initial begin $display(\"TEST PASSED\"); $finish; end endmodule\n",
        encoding="utf-8",
    )

    rtl_file, tb_file = controller._materialize_artifacts(
        build_spec_from_task(CRC8_REQUEST, "crc8_stream_accel"),
        prefer_workflow=True,
    )
    assert rtl_file == "crc8_stream_accel.v"
    rtl_text = (controller.rtl_dir / rtl_file).read_text(encoding="utf-8")
    assert "generated" in rtl_text
    assert "salvage" not in rtl_text
    assert tb_file == "crc8_stream_accel_tb.v"


def test_mission_round2_no_force_flag(tmp_path, monkeypatch):
    from cktclaw.agents.mission_control import ChipMissionControl

    captured_tasks: list[str] = []

    async def _fake_run(self, task, *, context=None):
        captured_tasks.append(task)
        return {
            "role_id": "eda_agent",
            "status": "failed" if len(captured_tasks) == 1 else "completed",
            "output": "## chip-autodesign\n**Status:** FAIL" if len(captured_tasks) == 1 else "## chip-autodesign\n**Status:** PASS",
            "artifacts": [],
            "error": None if len(captured_tasks) > 1 else "simulation failed",
            "steps": [],
        }

    monkeypatch.setattr(
        "cktclaw.agents.runners.eda_agent_runner.EDAAgentRunner.run",
        _fake_run,
    )

    async def _fake_optimizer(self, step, phases, mission_round=1):
        from cktclaw.agents.mission_control import MissionPhaseResult
        return MissionPhaseResult(
            phase=step.phase,
            role_id=step.role_id,
            status="completed",
            output="recommend iteration",
            artifacts=[],
        )

    monkeypatch.setattr(
        "cktclaw.agents.mission_control.ChipMissionControl._run_optimizer_agent",
        _fake_optimizer,
    )

    async def _noop_repair(self, eda_phase, mission_round):
        return None

    monkeypatch.setattr(
        "cktclaw.agents.mission_control.ChipMissionControl._dispatch_mission_repair",
        _noop_repair,
    )

    async def _run():
        mission = ChipMissionControl(
            "design crc8_stream_accel IP",
            project_dir=tmp_path / "mission_no_force_round2",
            force=True,
            max_mission_rounds=2,
            progress_quiet=True,
        )
        return await mission.run()

    result = asyncio.run(_run())
    assert result.status == "PASS"
    assert len(captured_tasks) >= 2
    assert "--force" in captured_tasks[0]
    assert "--force" not in captured_tasks[1]


def test_rtl_fence_normalizes_comment_path(tmp_path):
    from cktclaw.workflows.validated_rtl.cktclaw_llm_bridge import (
        extract_fenced_files_to_directory,
        normalize_verilog_generator_response,
        patch_workflow_rtl_responses,
    )

    fixture = Path(
        "/home/wjx/pythonproject/runs/chip_mission/97447b81379e/"
        "eda_autodesign/eda_validated_rtl/workflow/attempt-001/rtl/rtl_response.md"
    )
    if not fixture.is_file():
        raw = """```verilog
// rtl/crc8_stream_accel.v
module crc8_stream_accel(input clk); endmodule
```

```verilog
// tb/crc8_stream_accel_tb.v
module crc8_stream_accel_tb; initial $finish; endmodule
```"""
    else:
        raw = fixture.read_text(encoding="utf-8")

    normalized = normalize_verilog_generator_response(raw)
    assert "```verilog path=rtl/crc8_stream_accel.v" in normalized
    assert "```verilog path=tb/crc8_stream_accel_tb.v" in normalized

    workflow_dir = tmp_path / "workflow"
    rtl_dir = workflow_dir / "attempt-001" / "rtl"
    rtl_dir.mkdir(parents=True)
    response_path = rtl_dir / "rtl_response.md"
    response_path.write_text(raw, encoding="utf-8")
    patched = patch_workflow_rtl_responses(workflow_dir)
    assert "rtl/crc8_stream_accel.v" in patched

    dest = tmp_path / "extracted"
    written = extract_fenced_files_to_directory(response_path.read_text(encoding="utf-8"), dest)
    assert any("crc8_stream_accel.v" in path for path in written)
    assert (dest / "rtl" / "crc8_stream_accel.v").is_file()


def test_observability_no_false_completed_on_materialization_fail(tmp_path):
    from cktclaw.workflows.validated_rtl.observability import format_rtl_llm_cli_summary

    trace_dir = tmp_path / "eda_autodesign" / "eda_validated_rtl" / "reports"
    trace_dir.mkdir(parents=True)
    trace_dir.joinpath("workflow_trace.json").write_text(
        json.dumps(
            {
                "rtl_llm_provider": "command",
                "rtl_llm_called": True,
                "rtl_llm_status": "completed",
                "generation_mode": "salvage",
                "materialization_failed": True,
                "workflow_error": "Missing fenced code block",
            }
        ),
        encoding="utf-8",
    )
    summary = format_rtl_llm_cli_summary(tmp_path, overall_status="FAIL")
    assert "called but EDA failed" in summary or "materialization failed" in summary
    assert summary.endswith("(called)") is False


def test_mission_repair_dispatch_survives_errors(tmp_path, monkeypatch):
    from cktclaw.agents.mission_control import ChipMissionControl, MissionPhaseResult

    async def _broken_specialist(*args, **kwargs):
        raise ImportError("simulated repair failure")

    monkeypatch.setattr(
        "cktclaw.agents.runners.specialist_runner.run_specialist_role",
        _broken_specialist,
    )

    mission = ChipMissionControl(
        CRC8_REQUEST,
        project_dir=tmp_path / "repair_dispatch",
        progress_quiet=True,
    )
    phase = MissionPhaseResult(
        phase="eda_execute",
        role_id="eda_agent",
        status="failed",
        output="fail",
        error="compile failed",
    )

    async def _run():
        await mission._dispatch_mission_repair(phase, mission_round=1)

    asyncio.run(_run())


def test_rtl_repair_skill_applies_deterministic_tb_patch(tmp_path):
    from cktclaw.skills import rtl_repair_skill

    eda_dir = tmp_path / "eda_validated_rtl"
    reports = eda_dir / "reports"
    reports.mkdir(parents=True)
    (reports / "simulation.log").write_text(
        "error: Subroutine ports with unpacked dimensions are not yet supported\n",
        encoding="utf-8",
    )

    result = asyncio.run(
        rtl_repair_skill.rtl_repair_executor(
            "fix compile failure",
            {
                "eda_project_dir": str(eda_dir),
                "module_name": "crc8_stream_accel",
            },
        )
    )
    text = result[0]["text"]
    assert "Deterministic repair" in text
    assert (eda_dir / "tb" / "crc8_stream_accel_tb.v").is_file()


def test_soft_salvage_continues_after_workflow_fail(tmp_path, monkeypatch):
    from cktclaw.workflows.validated_rtl.adapter_loader import load_verilog_adapter

    adapter = load_verilog_adapter()
    assert adapter.ok, adapter.error

    def _failed_workflow(**kwargs):
        out_dir = Path(kwargs["out_dir"])
        rtl_path = out_dir / "attempt-001" / "rtl" / "generated" / "rtl" / "crc8_stream_accel.v"
        rtl_path.parent.mkdir(parents=True, exist_ok=True)
        rtl_path.write_text(
            "module crc8_stream_accel(input clk, input rst_n); endmodule\n",
            encoding="utf-8",
        )
        tb_path = out_dir / "attempt-001" / "rtl" / "generated" / "tb" / "crc8_stream_accel_tb.v"
        tb_path.parent.mkdir(parents=True, exist_ok=True)
        tb_path.write_text(
            "module crc8_stream_accel_tb; initial begin $display(\"ALL TESTS PASSED\"); $finish; end endmodule\n",
            encoding="utf-8",
        )
        return {
            "status": "failed",
            "attempts": [{"error": "Expecting ',' delimiter: line 23 column 57"}],
        }

    original_load = load_verilog_adapter

    def _patched_load(**kwargs):
        result = original_load(**kwargs)
        if result.ok and result.module is not None:
            result.module.run_verilog_workflow = _failed_workflow
        return result

    monkeypatch.setattr(
        "cktclaw.workflows.validated_rtl.controller.load_verilog_adapter",
        _patched_load,
    )

    async def _run():
        monkeypatch.setenv("CKTCLAW_VALIDATED_RTL_MOCK", "1")
        controller = ValidatedRTLController(
            CRC8_REQUEST,
            project_dir=tmp_path / "salvage",
            use_mock_provider=True,
            force=True,
            max_repair_rounds=1,
        )
        return await controller.run()

    result = asyncio.run(_run())
    root = Path(result.project_dir)
    trace = json.loads((root / "reports" / "workflow_trace.json").read_text(encoding="utf-8"))
    assert trace.get("generation_mode") in {"salvage", "workflow_salvaged"}
    assert "constraint_failed" in str(trace.get("rtl_llm_status", ""))
    assert (root / "rtl" / "crc8_stream_accel.v").is_file()
    assert (root / "reports" / "hard_gate_report.md").is_file()
    assert result.workflow_status == "failed"
