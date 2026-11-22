"""Tests for orchestrator Pydantic plan schema."""
import pytest
from pydantic import ValidationError


def test_valid_pass_result():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"stage": "chip-rtl", "status": "PASS", "qor": {}, "issues": []}
    result = validate_stage_result(raw, "chip-rtl")
    assert result["status"] == "PASS" and result["stage"] == "chip-rtl"


def test_stage_defaults_to_argument():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"status": "FAIL", "qor": {}}
    result = validate_stage_result(raw, "chip-synthesis")
    assert result["stage"] == "chip-synthesis"


def test_invalid_status_raises():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"stage": "chip-rtl", "status": "UNKNOWN", "qor": {}}
    with pytest.raises((ValidationError, ValueError)):
        validate_stage_result(raw, "chip-rtl")


def test_non_dict_qor_is_coerced():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"stage": "chip-sta", "status": "WARN", "qor": "some string"}
    result = validate_stage_result(raw, "chip-sta")
    assert isinstance(result["qor"], dict)


def test_bare_string_issues_coerced():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"stage": "chip-rtl", "status": "WARN", "qor": {},
           "issues": ["missing always block"]}
    result = validate_stage_result(raw, "chip-rtl")
    assert isinstance(result["issues"][0], dict)
    assert result["issues"][0]["description"] == "missing always block"


def test_non_dict_raises_value_error():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    with pytest.raises(ValueError, match="must be a dict"):
        validate_stage_result("not a dict", "chip-rtl")


def test_to_engine_dict_round_trip():
    from cktclaw.orchestrator.plan_schema import StageResult
    model = StageResult(stage="chip-synthesis", status="PASS",
                        qor={"area": 1000}, issues=[], recommendation="proceed")
    d = model.to_engine_dict()
    assert d["status"] == "PASS" and d["qor"]["area"] == 1000


def test_fail_status_preserved():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"stage": "chip-formal", "status": "FAIL", "qor": {},
           "issues": [{"severity": "FAIL", "description": "assertion fails"}]}
    result = validate_stage_result(raw, "chip-formal")
    assert result["status"] == "FAIL"


def test_ok_status_normalizes_to_pass_with_issue():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {"stage": "chip-rtl", "status": "OK", "qor": {}, "issues": []}
    result = validate_stage_result(raw, "chip-rtl")
    assert result["status"] == "PASS"
    assert any("OK normalized to PASS" in issue["description"] for issue in result["issues"])


def test_non_terminal_status_normalizes_to_warn_with_issue():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    for status in ["RUNNING", "PENDING", "IN_PROGRESS"]:
        result = validate_stage_result({"stage": "chip-rtl", "status": status, "qor": {}}, "chip-rtl")
        assert result["status"] == "WARN"
        assert any("Non-terminal status" in issue["description"] for issue in result["issues"])


def test_failed_status_normalizes_to_fail():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    result = validate_stage_result({"stage": "chip-rtl", "status": "FAILED", "qor": {}}, "chip-rtl")
    assert result["status"] == "FAIL"


def test_warn_stage_is_not_counted_as_passed():
    from cktclaw.orchestrator.parser import OrchestratorSpec
    from cktclaw.orchestrator.state_machine import OrchestratorStateMachine

    sm = OrchestratorStateMachine(OrchestratorSpec(name="x", stages=["a", "b"]))
    assert sm.start() == "a"
    transition = sm.complete_stage("a", "WARN")
    assert transition.action == "proceed"
    assert sm.stages["a"].status == "skipped"
