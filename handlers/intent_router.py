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
    # RTL-CLAW pipeline skills (specific patterns before generic chip-rtl)
    ("rtl-spec-analyzer", [
        r"\b(analyze.*spec|spec.*rtl|signal.*pin.*map)",
        r"(规格.*分析|分析.*规格|信号.{0,4}映射|功能点.*映射)",
        r"\b(rtl.?spec.?analyz|extract.*signal.*mapping)",
    ]),
    ("testbench-generator", [
        r"\b(generate.*testbench|tb.*gen|testbench.*gen|testbench.*creat)",
        r"(生成.*testbench|测试台生成|生成.*测试台|tb.*生成)",
    ]),
    ("verilog-partition", [
        r"\b(partition.*verilog|split.*rtl|rtl.*partition|verilog.*partition)",
        r"(分割.{0,6}(rtl|verilog|模块)|拆分.{0,6}(rtl|verilog)|verilog.*分割|RTL分区)",
    ]),
    ("verilog-optimization", [
        r"\b(optimize.*verilog|rtl.*optim|verilog.*optimize|partition.*optim)",
        r"(verilog.*优化|优化.{0,4}(RTL|rtl|verilog)|子模块.*优化|优化.*子模块)",
    ]),
    ("verilog-merge", [
        r"\b(merge.*verilog|rtl.*merge|verilog.*merge|merge.*submodule)",
        r"(verilog.*合并|合并.{0,6}(模块|verilog|子模块)|合并.*分割)",
        r"(分割后.{0,6}合并|分割.{0,10}合并|合并.{0,3}分割)",
    ]),
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
    ("chip-pipeline", [
        r"\b(fix_request|fix.?request|cross.?domain.?pipeline|pipeline.?orchestrat)",
        r"(验证.*RTL.*修复|闭环.*验证|fix_requests|跨域.*编排)",
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


# High-specificity skills have compound/domain-specific patterns — a single
# strong keyword hit (e.g. "fpv", "openroad", "nextpnr") is enough to route.
_HIGH_SPECIFICITY: frozenset = frozenset({
    "chip-formal", "chip-hls", "chip-compiler", "chip-infrastructure",
    "chip-dft", "chip-pd", "chip-soc", "chip-firmware", "chip-fpga", "chip-pipeline",
    "rtl-spec-analyzer", "testbench-generator", "verilog-partition",
    "verilog-optimization", "verilog-merge",
})
# Generic chip terms that must NOT route when sent on their own (no surrounding
# request context). A bare "verilog" is chat noise; "write a verilog module" is a
# real request. rtl/synth/etc. are < 6 chars and already filtered by length.
_GENERIC_THRESHOLD: int = 2
_BARE_GENERIC_KEYWORDS: frozenset = frozenset({
    "verilog", "systemverilog", "rtl", "hdl", "cdc", "lint",
    "synth", "synthesis", "netlist", "sta", "timing", "dft",
    "fpga", "soc", "hls", "pd", "verification", "uvm", "cts",
})

_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)


def _is_bare_keyword(text: str) -> bool:
    """True when *text* is nothing but a single generic chip keyword."""
    token = _NON_WORD.sub("", text.lower())
    return token in _BARE_GENERIC_KEYWORDS


def detect_chip_design_intent(user_input: str) -> Optional[str]:
    """
    Determine if *user_input* should be routed to a chip-design orchestrator.

    Scoring counts individual keyword occurrences (not just matching patterns),
    so a compound request like "write an RTL module and run lint" outweighs a
    bare keyword. A message that is *only* a generic keyword ("verilog") is
    treated as chat and not routed; the same keyword inside a real request
    ("write a verilog module") still routes.

    Returns:
        The skill name (e.g. ``"chip-synthesis"``) if matched, or ``None``
        if the input should go through the normal chat path.
    """
    text = user_input.strip()

    if len(text) < 6:
        return None

    if _CHAT_INDICATORS.search(text):
        return None

    # A message consisting solely of a generic keyword is chat, not a request.
    if _is_bare_keyword(text):
        return None

    scores: dict[str, int] = {}
    for skill, patterns in _COMPILED_RULES:
        hits = sum(len(p.findall(text)) for p in patterns)
        if hits:
            scores[skill] = hits

    if not scores:
        return None

    best_skill = max(scores, key=scores.get)
    best_score = scores[best_skill]

    if best_score >= 1:
        return best_skill

    return None


def detect_chip_design_intent_with_confidence(user_input: str) -> Optional[dict]:
    """
    Like detect_chip_design_intent but returns routing metadata with numeric confidence.

    confidence mapping:
      - score >= 2  -> 0.92
      - score == 1  -> 0.75
    """
    text = user_input.strip()

    if len(text) < 6:
        return None

    if _CHAT_INDICATORS.search(text):
        return None

    if _is_bare_keyword(text):
        return None

    scores: dict[str, int] = {}
    for skill, patterns in _COMPILED_RULES:
        hits = sum(len(p.findall(text)) for p in patterns)
        if hits:
            scores[skill] = hits

    if not scores:
        return None

    best_skill = max(scores, key=scores.get)
    best_score = scores[best_skill]
    if best_score < 1:
        return None

    confidence = 0.92 if best_score >= 2 else 0.75
    return {
        "skill_id": best_skill,
        "confidence": confidence,
        "score": best_score,
        "needs_orchestrator": best_skill.startswith("chip-"),
        "task": text,
        "rationale": "keyword fast-path match",
    }
