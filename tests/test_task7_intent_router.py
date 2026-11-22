"""Tests for intent router minimum-score guard."""
import pytest
from cktclaw.handlers.intent_router import detect_chip_design_intent, resolve_chip_intent


def test_bare_verilog_not_routed():
    assert detect_chip_design_intent("verilog") is None


def test_bare_rtl_not_routed():
    assert detect_chip_design_intent("rtl") is None


def test_compound_rtl_with_lint_routes_to_chip_rtl():
    result = detect_chip_design_intent("write an RTL module and run lint on it")
    assert result == "chip-rtl"


def test_multi_agent_chip_task_routes_to_chip_mission():
    result = detect_chip_design_intent(
        "让七个agent自助决策调用skill和tool完成这个芯片设计任务"
    )
    assert result == "chip-mission"


def test_autodesign_flow_routes_to_chip_autodesign():
    result = detect_chip_design_intent(
        "从规格和plan开始自动完成RTL仿真综合QoR"
    )
    assert result == "chip-autodesign"


def test_verilog_plus_self_checking_testbench_routes_to_erie_generator():
    result = detect_chip_design_intent(
        "Generate a parameterized FIFO RTL and a self-checking testbench"
    )
    assert result == "erie-verilog-generator"


def test_crc8_full_pipeline_routes_to_chip_mission_not_erie():
    from cktclaw.handlers.intent_router import resolve_chip_intent

    text = (
        "设计 CRC-8 streaming accelerator，模块名 crc8_stream_accel，"
        "生成 RTL、self-checking testbench、仿真脚本和 Yosys 综合脚本，"
        "失败自动修复最多5轮，最终 hard gate 报告"
    )
    intent = resolve_chip_intent(text)
    assert intent.route == "chip-mission"
    assert detect_chip_design_intent(text) == "chip-mission"


def test_plain_testbench_generation_stays_on_rtl_claw_testbench_skill():
    result = detect_chip_design_intent("generate a testbench for the existing FIFO design")
    assert result == "testbench-generator"


def test_formal_verification_routes_at_score_1():
    result = detect_chip_design_intent("run formal verification with FPV")
    assert result == "chip-formal"


def test_hello_not_routed():
    assert detect_chip_design_intent("你好，help me please") is None


def test_what_is_cktclaw_not_routed():
    assert detect_chip_design_intent("what is cktclaw") is None


def test_bare_synth_not_routed():
    assert detect_chip_design_intent("synth") is None


def test_synthesis_with_netlist_routes():
    result = detect_chip_design_intent("synthesize the design and produce a gate-level netlist")
    assert result == "chip-synthesis"


def test_unrelated_not_routed():
    assert detect_chip_design_intent("what is the weather today") is None


def test_tiny_npu_digit6_chinese_routes_to_chip_mission():
    result = detect_chip_design_intent(
        "请你为我设计一个可运行的tiny_npu并且该芯片可以实现数字手势“6”的识别测试。"
    )
    assert result == "chip-mission"


def test_tiny_npu_underscore_routes_to_chip_flow():
    result = detect_chip_design_intent("tiny_npu digit 6 recognition test")
    assert result in {"chip-mission", "chip-autodesign"}


def test_tiny_npu_gesture_routes_to_chip_flow():
    result = detect_chip_design_intent("Tiny NPU 手势识别")
    assert result in {"chip-mission", "chip-autodesign"}


def test_unknown_crc_offload_ip_routes_to_chip_mission():
    intent = resolve_chip_intent("design a CRC offload IP with RTL verification and synthesis")
    assert intent.is_chip_task
    assert intent.route == "chip-mission"
    assert intent.task_domain == "rtl_design"


def test_unknown_sparse_attention_block_routes_to_chip_mission():
    result = detect_chip_design_intent("build a systolic sparse attention block for inference")
    assert result == "chip-mission"


def test_pwm_motor_control_chinese_routes_to_chip_mission():
    result = detect_chip_design_intent("实现一个电机控制 PWM 芯片模块，并完成仿真验证")
    assert result == "chip-mission"


def test_single_point_synthesis_still_routes_to_synthesis():
    result = detect_chip_design_intent("only run synthesis and produce a gate-level netlist")
    assert result == "chip-synthesis"


def test_resolve_chip_intent_exposes_structured_fields():
    intent = resolve_chip_intent("build a DMA controller IP with tests")
    data = intent.to_dict()
    assert data["is_chip_task"] is True
    assert data["route"] == "chip-mission"
    assert "controller" in data["design_object"].lower() or data["design_object"]
