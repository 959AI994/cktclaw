"""
Intent Router — detect whether a natural-language user message should be
routed to a chip-design orchestrator skill instead of the generic chat path.

Uses a keyword-based first pass for speed; falls back to LLM classification
only when the keyword pass is ambiguous.
"""

import re
from typing import Optional

# Keyword → skill mapping.  Order matters: more specific patterns first.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    # Higher-specificity domains first to avoid false matches
    ("chip-formal", [
        r"\b(formal.?verif|形式验证|fpv|property.?check|assert.*proof|symbiyosys|sby\b)",
        r"\b(model.?check|bounded.?proof|formal.?proof)",
    ]),
    ("chip-hls", [
        r"\b(hls\b|high.?level.?synth|bambu|vivado.?hls|高层次综合)",
        r"(c\+?\+?|cpp)\s*(to|转)\s*rtl",
    ]),
    ("chip-compiler", [
        r"\b(llvm.?backend|gcc.?backend|编译器后端|assembler.*isa|linker.*isa)",
        r"\b(compiler.?toolchain|工具链.*isa|custom.?isa.*(compiler|backend))",
    ]),
    ("chip-infrastructure", [
        r"\b(eda.?tool.?detect|wrapper.?deploy|mcp.?config|工具检测|环境搭建)",
        r"\b(detect.*(eda|tool)|检测.*工具|setup.*eda)",
    ]),
    ("chip-synthesis", [
        r"\b(synth|综合|yosys\b.*synth|logic.?synth|netlist|gate.?level|compile.*rtl)",
        r"\b(lec|逻辑等价|equivalence.?check)",
    ]),
    ("chip-verification", [
        r"\b(uvm|testbench|tb\b|coverage|regression|cocotb|iverilog.*sim)",
        r"\b(constrained.?random|功能验证|test.?plan|仿真)",
        r"验证.{0,6}(功能|模块|设计|电路|RTL|逻辑)",
    ]),
    ("chip-rtl", [
        r"\b(rtl|verilog|systemverilog|lint|cdc)",
        r"(写|编写|设计|design).{0,8}(模块|module|rtl|hdl)",
    ]),
    ("chip-sta", [
        r"\b(sta\b|timing.?analy|时序分析|opensta|slack|setup.?time|hold.?time|critical.?path)",
        r"\b(multi.?corner|timing.?report|wns\b|tns\b)",
    ]),
    ("chip-pd", [
        r"\b(physical.?design|floorplan|placement|routing|cts|clock.?tree|布局布线)",
        r"\b(openroad|def\b.*gds|signoff.?drc|power.?grid)",
    ]),
    ("chip-architecture", [
        r"\b(微架构|micro.?arch|pipeline.?design|架构探索|design.?space.?explor)",
        r"\b(ppa.?estimat|chip.?architect)",
    ]),
    ("chip-dft", [
        r"\b(dft\b|scan.?chain|atpg|bist|mbist|jtag|boundary.?scan|可测试性)",
    ]),
    ("chip-soc", [
        r"\b(soc\b|ip.?integrat|bus.?fabric|axi\b.*interconnect|chip.?level.?sim|片上系统)",
    ]),
    ("chip-firmware", [
        r"\b(firmware|bsp|rtos|嵌入式|embedded|固件)",
        r"(驱动|driver).{0,6}(外设|peripheral|开发)",
    ]),
    ("chip-fpga", [
        r"\b(fpga|bitstream|nextpnr|openFPGA|fpga.?prototyp|fpga.?emulat)",
    ]),
]

# Compile patterns once
_COMPILED_RULES: list[tuple[str, list[re.Pattern]]] = [
    (skill, [re.compile(p, re.IGNORECASE) for p in patterns])
    for skill, patterns in _KEYWORD_RULES
]

# Terms that strongly indicate generic chat, not chip design
_CHAT_INDICATORS = re.compile(
    r"\b(你好|hello|hi\b|what is cktclaw|help|帮助|介绍|about|"
    r"how.?to.?use|什么是|explain.?yourself)\b",
    re.IGNORECASE,
)


def detect_chip_design_intent(user_input: str) -> Optional[str]:
    """
    Determine if *user_input* should be routed to a chip-design orchestrator.

    Returns:
        The skill name (e.g. ``"chip-synthesis"``) if matched, or ``None``
        if the input should go through the normal chat path.
    """
    text = user_input.strip()

    if len(text) < 6:
        return None

    if _CHAT_INDICATORS.search(text):
        return None

    scores: dict[str, int] = {}
    for skill, patterns in _COMPILED_RULES:
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            scores[skill] = hits

    if not scores:
        return None

    best_skill = max(scores, key=scores.get)
    best_score = scores[best_skill]

    # Require at least 1 keyword hit
    if best_score >= 1:
        return best_skill

    return None
