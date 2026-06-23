"""
Extract numeric QoR metrics from EDA tool stdout (Yosys / ABC / OpenSTA).

Used to supplement (not replace) LLM-reported QoR in orchestrator stages.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _extract_yosys_metrics(output: str) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    m = re.search(r"Number of cells:\s+(\d+)", output)
    if m:
        metrics["area_cells"] = int(m.group(1))
    m = re.search(r"Number of wires:\s+(\d+)", output)
    if m:
        metrics["wire_count"] = int(m.group(1))
    m = re.search(r"Chip area for module.*?:\s+([\d.]+)", output)
    if m:
        metrics["chip_area"] = float(m.group(1))
    if "ERROR" in output.upper():
        metrics["yosys_error"] = 1
    return metrics


def _extract_abc_metrics(output: str) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    m = re.search(r"and\s*=\s*(\d+)", output, re.I)
    if m:
        metrics["and_nodes"] = int(m.group(1))
    m = re.search(r"lev\s*=\s*(\d+)", output, re.I)
    if m:
        metrics["logic_levels"] = int(m.group(1))
    m = re.search(r"i/o\s*=\s*(\d+)\s*/\s*(\d+)", output, re.I)
    if m:
        metrics["abc_inputs"] = int(m.group(1))
        metrics["abc_outputs"] = int(m.group(2))
    return metrics


def _extract_sta_metrics(output: str) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    # WNS / slack patterns
    for pattern in [
        r"slack\s*[=(]\s*([-\d.]+)",
        r"wns\s*[:=]\s*([-\d.]+)",
    ]:
        m = re.search(pattern, output, re.I)
        if m:
            metrics["wns_ns"] = float(m.group(1))
            break
    m = re.search(r"tns\s*[:=]\s*([-\d.]+)", output, re.I)
    if m:
        metrics["tns_ns"] = float(m.group(1))
    m = re.search(r"delay\s*[:=]\s*([\d.]+)\s*ns", output, re.I)
    if m:
        metrics["delay_ns"] = float(m.group(1))
    return metrics


def extract_qor_from_text(text: str) -> Dict[str, Any]:
    """Parse a single tool output string for known metric patterns."""
    if not text or not isinstance(text, str):
        return {}
    merged: Dict[str, Any] = {}
    merged.update(_extract_yosys_metrics(text))
    merged.update(_extract_abc_metrics(text))
    merged.update(_extract_sta_metrics(text))
    return merged


def extract_qor_from_outputs(outputs: List[str]) -> Dict[str, Any]:
    """Merge metrics from multiple tool outputs in one stage."""
    merged: Dict[str, Any] = {}
    for chunk in outputs:
        for k, v in extract_qor_from_text(chunk).items():
            merged[k] = v
    return merged


def merge_qor(llm_qor: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge LLM-reported QoR with tool-extracted metrics.

    Tool-extracted numeric values win when the LLM left a key empty or missing.
    """
    base = dict(llm_qor or {})
    for k, v in (extracted or {}).items():
        if k not in base or base[k] in (None, "", 0):
            base[k] = v
        elif isinstance(base[k], (int, float)) and isinstance(v, (int, float)):
            # Prefer extracted measurements over LLM guesses for known metric keys
            if k in (
                "area_cells", "and_nodes", "logic_levels", "wns_ns",
                "tns_ns", "delay_ns", "chip_area",
            ):
                base[k] = v
    return base
