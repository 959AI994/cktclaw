"""
VerilogMetricsExtractor - Domain-specific Verilog parsing utilities.

Extracts structural metrics, builds analysis prompts, and provides
fallback analysis when LLM is unavailable. No LLM communication here.
"""

import re
from typing import Any, Dict


class VerilogMetricsExtractor:
    """Pure Verilog code parsing and metrics extraction."""

    @staticmethod
    def extract_metrics(code: str) -> Dict[str, Any]:
        """Extract basic structural and complexity metrics from Verilog code."""
        return {
            "code_length": len(code),
            "lines_of_code": len([l for l in code.split('\n') if l.strip()]),
            "structure": {
                "modules": len(re.findall(r'\bmodule\b', code, re.IGNORECASE)),
                "inputs": len(re.findall(r'\binput\b', code, re.IGNORECASE)),
                "outputs": len(re.findall(r'\boutput\b', code, re.IGNORECASE)),
                "wires": len(re.findall(r'\bwire\b', code, re.IGNORECASE)),
                "regs": len(re.findall(r'\breg\b', code, re.IGNORECASE)),
            },
            "complexity": {
                "always_blocks": len(re.findall(r'\balways\b', code, re.IGNORECASE)),
                "assign_statements": len(re.findall(r'\bassign\b', code, re.IGNORECASE)),
                "case_statements": len(re.findall(r'\bcase\b', code, re.IGNORECASE)),
            },
        }

    @staticmethod
    def build_analysis_prompt(verilog_code: str, metrics: Dict[str, Any]) -> str:
        """Build a structured analysis prompt for the LLM."""
        return f"""Analyze the following Verilog code and provide a detailed functional analysis report.

**Verilog Code:**
```verilog
{verilog_code}
```

**Basic Metrics:**
- Inputs: {metrics['structure']['inputs']}
- Outputs: {metrics['structure']['outputs']}
- Registers: {metrics['structure']['regs']}
- Always Blocks: {metrics['complexity']['always_blocks']}
- Assign Statements: {metrics['complexity']['assign_statements']}

**Please provide:**

1. **Functional Description**: What does this circuit do? What is its primary purpose?

2. **Architecture Analysis**:
   - Is it combinational or sequential logic?
   - What design patterns are used?
   - Any state machines or special structures?

3. **Input/Output Behavior**:
   - Describe the relationship between inputs and outputs
   - Any data transformations or operations?

4. **Implementation Quality**:
   - Code quality assessment
   - Potential issues or optimizations
   - Synthesis considerations

5. **Application Context**:
   - What type of circuit is this likely to be (adder, multiplexer, FSM, etc.)?
   - Typical use cases

Format the response in markdown with clear sections."""

    @staticmethod
    def generate_fallback_analysis(code: str, metrics: Dict[str, Any]) -> str:
        """Rule-based fallback analysis when LLM is unavailable."""
        lines = []
        lines.append("## Functional Analysis\n")

        has_always = metrics['complexity']['always_blocks'] > 0
        has_assign = metrics['complexity']['assign_statements'] > 0
        has_case = metrics['complexity']['case_statements'] > 0
        has_regs = metrics['structure']['regs'] > 0

        if has_regs and has_always:
            lines.append("**Circuit Type**: Sequential Logic")
            lines.append("- Contains registers and always blocks, indicating stateful behavior")
        elif has_assign and not has_regs:
            lines.append("**Circuit Type**: Combinational Logic")
            lines.append("- Uses continuous assignments, purely combinational")
        else:
            lines.append("**Circuit Type**: Mixed Logic")
            lines.append("- Combines both sequential and combinational elements")

        lines.append("")
        lines.append("**Structural Overview**:")
        lines.append(f"- {metrics['structure']['inputs']} input port(s)")
        lines.append(f"- {metrics['structure']['outputs']} output port(s)")

        if has_case:
            lines.append("\n**Design Pattern**: Likely contains state machine or multiplexer logic (case statements detected)")

        lines.append("\n*Note: This is a basic structural analysis. For detailed functional analysis, LLM service is required.*")

        return "\n".join(lines)
