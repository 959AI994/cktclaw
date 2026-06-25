"""Tests for intent router minimum-score guard."""
import pytest
from cktclaw.handlers.intent_router import detect_chip_design_intent


def test_bare_verilog_not_routed():
    assert detect_chip_design_intent("verilog") is None


def test_bare_rtl_not_routed():
    assert detect_chip_design_intent("rtl") is None


def test_compound_rtl_with_lint_routes_to_chip_rtl():
    result = detect_chip_design_intent("write an RTL module and run lint on it")
    assert result == "chip-rtl"


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
