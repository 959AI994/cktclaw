"""
Stress tests for intent routing — Fix 1 & 2 (intent routing + state transitions).

Tests adversarial / edge-case scenarios that the happy-path test suite misses:
  - Intent hijacking: chat session suddenly receives an EDA command
  - Domain consistency: same-domain prompts must route consistently
  - Graceful handling: extreme inputs (very long, special chars, unicode) must not crash
  - Ambiguous fallback: prompts that could match multiple domains return predictably
  - Bilingual (Chinese/English mixed): correct routing for mixed-language inputs
"""

import sys
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.handlers.intent_router import detect_chip_design_intent


# ═══════════════════════════════════════════════════════════════
# 1. Intent Hijack from Chat
# ═══════════════════════════════════════════════════════════════

class TestIntentHijackFromChat:
    """
    Simulate a session where generic chat is followed by a sudden EDA command.
    The router must switch domains correctly (stateless routing).
    """

    def test_intent_hijack_from_chat(self):
        """Generic chat → sudden EDA command must route to chip-synthesis."""
        # Turn 1: generic chat
        assert detect_chip_design_intent("hello, what can you do?") is None

        # Turn 2: sudden EDA hijack
        result = detect_chip_design_intent("synthesize my adder design with Yosys")
        assert result == "chip-synthesis"

    def test_chat_then_rtl_hijack(self):
        """Chat → RTL command must switch correctly."""
        assert detect_chip_design_intent("how do I get started?") is None
        assert detect_chip_design_intent("write a verilog module for FIFO") == "chip-rtl"

    def test_chat_then_sta_hijack(self):
        """Chat → STA command must switch correctly."""
        assert detect_chip_design_intent("thank you for your help") is None
        assert detect_chip_design_intent("run timing analysis with OpenSTA") == "chip-sta"

    def test_no_state_leak_between_calls(self):
        """
        Router is stateless — prior generic chat must not corrupt EDA routing.
        """
        # Multiple chat turns
        for prompt in ["hello", "you好", "what is CktClaw?"]:
            assert detect_chip_design_intent(prompt) is None

        # EDA routing must still work correctly after chat turns
        assert detect_chip_design_intent("run logic synthesis on the top module") == "chip-synthesis"
        assert detect_chip_design_intent("build a UVM testbench for FIFO") == "chip-verification"
        assert detect_chip_design_intent("run placement and routing on my design") == "chip-pd"

    def test_eda_to_chat_to_eda(self):
        """EDA → chat → EDA must all route correctly."""
        assert detect_chip_design_intent("synthesize my adder") == "chip-synthesis"
        assert detect_chip_design_intent("hello there") is None
        assert detect_chip_design_intent("use SymbiYosys to prove assertions") == "chip-formal"


# ═══════════════════════════════════════════════════════════════
# 2. Intent Stays on Domain (Multi-turn Consistency)
# ═══════════════════════════════════════════════════════════════

class TestIntentStaysOnDomain:
    """
    Multi-turn simulation: five prompts for the same domain must all route consistently.
    """

    def test_intent_stays_on_synthesis_domain(self):
        """Five chip-synthesis prompts must all return 'chip-synthesis'."""
        prompts = [
            "synthesize my adder design with Yosys",
            "run logic synthesis on the top module",
            "compile the RTL to gate-level netlist",
            "generate netlist from verilog",
            "logic synthesis flow for low power",
        ]
        for prompt in prompts:
            result = detect_chip_design_intent(prompt)
            assert result == "chip-synthesis", (
                f"Consistency broken: '{prompt}' -> {result}, expected chip-synthesis"
            )

    def test_intent_stays_on_rtl_domain(self):
        """Five chip-rtl prompts must all return 'chip-rtl'."""
        prompts = [
            "write a verilog module for FIFO",
            "design an RTL module for AXI master",
            "write SystemVerilog code for a shift register",
            "design a pipelined multiplier in verilog",
            "implement a UART receiver in RTL",
        ]
        for prompt in prompts:
            result = detect_chip_design_intent(prompt)
            assert result == "chip-rtl", (
                f"Consistency broken: '{prompt}' -> {result}, expected chip-rtl"
            )

    def test_domain_isolation_across_domains(self):
        """Different domain prompts must route to their correct respective domains."""
        domain_cases = [
            ("write a verilog module for FIFO", "chip-rtl"),
            ("run timing analysis with OpenSTA", "chip-sta"),
            ("build a UVM testbench for FIFO", "chip-verification"),
            ("run placement and routing on my design", "chip-pd"),
            ("use SymbiYosys to prove assertions", "chip-formal"),
        ]
        for prompt, expected in domain_cases:
            result = detect_chip_design_intent(prompt)
            assert result == expected, f"'{prompt}' -> {result}, expected {expected}"


# ═══════════════════════════════════════════════════════════════
# 3. Graceful Preempt (Edge-Case Inputs Must Not Crash)
# ═══════════════════════════════════════════════════════════════

class TestGracefulPreempt:
    """
    Tests that extreme or adversarial inputs do not crash the router.
    In production, these arrive via async cancel, interrupted streams,
    or malicious user input.
    """

    def test_very_short_inputs_return_none(self):
        """Inputs shorter than 6 characters must return None without crashing."""
        for short in ["", "  ", "hi", "abc", "     ", "\n"]:
            result = detect_chip_design_intent(short)
            assert result is None, f"Short input '{repr(short)}' should return None"

    def test_very_long_input_does_not_crash(self):
        """Very long input (100k chars) must complete without exception."""
        long_input = "synthesize " + "a" * 100_000
        start = time.time()
        try:
            result = detect_chip_design_intent(long_input)
            assert isinstance(result, (str, type(None)))
        except Exception as e:
            pytest.fail(f"Router crashed on long input: {e}")
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Router took too long on long input: {elapsed:.2f}s"

    def test_special_characters_do_not_crash(self):
        """Special characters (null bytes, injection patterns) must not crash router."""
        special_inputs = [
            "synth \x00\x01\x02",
            "synthesize <script>alert('xss')</script>",
            "synth; rm -rf /",
            "synthesize `ls -la`",
            "\n\n\n\nsynthesize\n\n",
            "\r\nsynthesize\r\n",
        ]
        for inp in special_inputs:
            try:
                result = detect_chip_design_intent(inp)
                assert isinstance(result, (str, type(None))), (
                    f"Unexpected result type for '{inp[:50]}': {type(result)}"
                )
            except Exception as e:
                pytest.fail(f"Router crashed on special input '{inp[:50]}': {e}")

    def test_unicode_inputs_do_not_crash(self):
        """Unicode characters including emojis must not crash the router."""
        unicode_inputs = [
            "综合这个模块🔧",
            "⚡ synthesize my design",
            "RTL设计模块 with 特殊字符",
            "\u200b\u200csynthesize",  # Zero-width characters
            "🚀💡🔬 synthesize",
        ]
        for inp in unicode_inputs:
            try:
                result = detect_chip_design_intent(inp)
                assert isinstance(result, (str, type(None)))
            except Exception as e:
                pytest.fail(f"Router crashed on unicode input '{inp}': {e}")

    def test_repeated_calls_are_fast(self):
        """Router must handle 1000 calls without significant slowdown (regex-based)."""
        prompt = "synthesize my adder design with Yosys"
        start = time.time()
        for _ in range(1000):
            detect_chip_design_intent(prompt)
        elapsed = time.time() - start
        assert elapsed < 2.0, f"1000 routing calls took {elapsed:.2f}s (expected <2s)"


# ═══════════════════════════════════════════════════════════════
# 4. Ambiguous Prompt Fallback
# ═══════════════════════════════════════════════════════════════

class TestAmbiguousPromptFallback:
    """
    Ambiguous prompts must either return None (fallback to LLM) or a valid
    chip domain — they must never hard-crash.
    """

    def test_ambiguous_test_prompt(self):
        """'write a test for my design' — ambiguous, could match verification or RTL."""
        result = detect_chip_design_intent("write a test for my design")
        # Must not crash; both None and any chip domain are valid
        assert result is None or result.startswith("chip-"), (
            f"Unexpected routing: {result}"
        )

    def test_general_design_prompt(self):
        """'design a module' alone is very generic."""
        result = detect_chip_design_intent("design a module")
        assert result is None or result.startswith("chip-")

    def test_nonchip_technical_prompts_return_none(self):
        """Non-chip technical prompts must return None."""
        non_chip_prompts = [
            "deploy my web application",
            "write a Python script for data processing",
            "create a database schema",
            "build a REST API with FastAPI",
            "configure nginx for load balancing",
        ]
        for prompt in non_chip_prompts:
            result = detect_chip_design_intent(prompt)
            assert result is None, f"'{prompt}' should return None, got {result}"

    def test_generic_coding_prompts_return_none(self):
        """Generic coding prompts unrelated to EDA must return None."""
        for prompt in [
            "what is 2 + 2?",
            "tell me a joke",
            "what's the weather today?",
            "goodbye",
            "nice work!",
        ]:
            result = detect_chip_design_intent(prompt)
            assert result is None, f"'{prompt}' should return None, got {result}"

    def test_partial_eda_keywords_can_fallback(self):
        """Partial EDA keywords without clear context may legitimately return None."""
        # These are borderline — must not crash
        borderline_prompts = [
            "I need to synthesize my thoughts",  # "synthesize" in non-EDA context
            "run some tests",
            "design a better workflow",
        ]
        for prompt in borderline_prompts:
            try:
                result = detect_chip_design_intent(prompt)
                # Result can be None or a chip domain — both are acceptable
                assert result is None or result.startswith("chip-")
            except Exception as e:
                pytest.fail(f"Router crashed on borderline prompt '{prompt}': {e}")


# ═══════════════════════════════════════════════════════════════
# 5. Chinese-English Mixed Prompts
# ═══════════════════════════════════════════════════════════════

class TestChineseEnglishMixed:
    """
    Bilingual (Chinese/English) EDA prompts must route correctly.
    CktClaw targets Chinese EDA engineers who mix languages naturally.
    """

    def test_chinese_synthesis_prompt(self):
        """Pure Chinese synthesis prompt must route to chip-synthesis."""
        assert detect_chip_design_intent("综合这个模块") == "chip-synthesis"

    def test_chinese_rtl_prompt(self):
        """Pure Chinese RTL prompt must route to chip-rtl."""
        assert detect_chip_design_intent("编写一个4位加法器模块") == "chip-rtl"

    def test_chinese_sta_prompt(self):
        """Pure Chinese STA prompt must route to chip-sta."""
        assert detect_chip_design_intent("时序分析这个设计") == "chip-sta"

    def test_chinese_verification_prompt(self):
        """Chinese verification prompt must route to chip-verification."""
        assert detect_chip_design_intent("功能验证这个RTL模块") == "chip-verification"

    def test_chinese_hls_prompt(self):
        """Chinese HLS prompt must route to chip-hls."""
        assert detect_chip_design_intent("高层次综合把C代码转成硬件") == "chip-hls"

    def test_chinese_pd_prompt(self):
        """Chinese PD prompt must route to chip-pd."""
        assert detect_chip_design_intent("布局布线我的设计") == "chip-pd"

    def test_mixed_language_synthesis_prompts(self):
        """Mixed Chinese-English synthesis prompts must not crash and should route."""
        mixed_prompts = [
            "用 Yosys 综合这个设计",
            "RTL综合 with low power settings",
            "compile 我的RTL代码 into gate-level",
        ]
        for prompt in mixed_prompts:
            try:
                result = detect_chip_design_intent(prompt)
                assert result is None or result.startswith("chip-"), (
                    f"Mixed prompt '{prompt}' routed to unexpected: {result}"
                )
            except Exception as e:
                pytest.fail(f"Router crashed on mixed-language prompt '{prompt}': {e}")

    def test_chinese_infrastructure_prompt(self):
        """Chinese tool detection prompt must route to chip-infrastructure."""
        assert detect_chip_design_intent("工具检测看看有哪些可用") == "chip-infrastructure"

    def test_chinese_chat_indicators_return_none(self):
        """Chinese chat indicators must return None, not route to chip domain."""
        for chat_prompt in [
            "你好，介绍一下自己",
            "帮助我了解功能",
            "关于CktClaw的介绍",
        ]:
            result = detect_chip_design_intent(chat_prompt)
            assert result is None, (
                f"Chinese chat prompt '{chat_prompt}' should return None, got {result}"
            )
