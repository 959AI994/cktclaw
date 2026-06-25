"""
RTL repair workflow skill.

This skill provides a CktClaw-native repair contract inspired by RTLFixer-style
compile/simulate feedback loops. If RTLFIXER_ROOT is set, the executor includes
the local RTLFixer path in the handoff context; the first implementation keeps
the workflow prompt-native so it can run without vendoring external code.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.harness import SkillDefinition, SkillType, LoadedFrom, register_skill


def get_rtlfixer_root() -> Path:
    env = os.environ.get("RTLFIXER_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return Path(__file__).parent.parent / "deps" / "RTLFixer"


async def rtl_repair_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = get_rtlfixer_root()
    root_note = (
        f"RTLFixer root detected: {root}"
        if (root / "src").is_dir()
        else f"RTLFixer root not installed at {root}; use native CktClaw repair workflow."
    )
    task = args.strip() or "No repair task provided."
    text = f"""# RTL Repair Workflow

{root_note}

## User Task

{task}

## Repair Contract

1. Reproduce the failure with the narrowest available gate:
   - `slang` or `verible` for syntax/elaboration/style.
   - `verilator` or simulator flow for compile/simulation failures.
   - `yosys` for synthesis failures.
   - `sby` for formal/property failures.
2. Classify the root cause:
   - syntax/parser issue
   - port/interface mismatch
   - reset/clocking issue
   - width/sign/packed-dimension issue
   - sequential behavior mismatch
   - synthesis-only unsupported construct
   - property/environment issue
3. Apply the smallest RTL or collateral edit that resolves the evidence.
4. Re-run the same failing gate, then one adjacent stronger gate when available.
5. Produce a repair report with commands, changed files, residual risk, and next gate.

## Output Required

- Root cause.
- Patch summary.
- Verification evidence.
- Remaining assumptions.
"""
    return [{"type": "text", "text": text}]


RTL_REPAIR_SKILL = SkillDefinition(
    name="rtl-repair",
    skill_type=SkillType.WORKFLOW,
    description=(
        "RTL compile/lint/simulation/formal repair workflow inspired by RTLFixer-style "
        "feedback loops."
    ),
    display_name="RTL Repair",
    aliases=["rtl-fixer", "rtlfixer", "verilog-repair", "rtl-debug"],
    when_to_use=(
        "Use when RTL fails syntax, lint, simulation, synthesis, or formal checks "
        "and the task is to diagnose and repair the design."
    ),
    argument_hint="Failure logs, RTL paths, testbench paths, and expected behavior",
    argument_names=["task"],
    allowed_tools=["Read", "Write", "Bash", "verible", "slang", "verilator", "yosys", "sby"],
    user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
    source="cktclaw",
    executor=rtl_repair_executor,
)


async def register_rtl_repair_skill() -> None:
    await register_skill(RTL_REPAIR_SKILL)
