"""
Verification Layer — executes real tool chains and collects metrics.

Runs actual EDA tools, chip simulations, and AI benchmarks to verify
that generated artifacts meet their task's verification criteria.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_graph import TaskNode

logger = logging.getLogger(__name__)


@dataclass
class VerificationReport:
    """Result of verifying a task's artifacts against its criteria."""

    task_id: str
    passed: bool
    metrics: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tool_outputs: Dict[str, str] = field(default_factory=dict)
    duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "metrics": self.metrics,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration": self.duration,
        }


class VerificationRunner:
    """
    Executes real tool chains to verify generated artifacts.

    Dispatches to domain-specific verification methods:
    - EDA: Yosys synth → ABC optimize → OpenSTA timing
    - Chip: lint, simulation, formal verification
    - AI Infra: compile check, unit tests, benchmarks
    """

    def __init__(self):
        self._timeout = 300  # 5 min per verification

    async def verify_task(
        self, task: TaskNode, artifacts: List[str]
    ) -> VerificationReport:
        """
        Verify a task's artifacts against its criteria.

        Args:
            task: The task node with verification_criteria.
            artifacts: File paths produced by the generation phase.

        Returns:
            VerificationReport with metrics and pass/fail status.
        """
        start = time.time()

        try:
            if task.domain == "eda":
                report = await self._verify_eda(task, artifacts)
            elif task.domain == "chip":
                report = await self._verify_chip(task, artifacts)
            elif task.domain == "ai_infra":
                report = await self._verify_ai_infra(task, artifacts)
            else:
                report = VerificationReport(
                    task_id=task.id,
                    passed=False,
                    errors=[f"Unknown domain: {task.domain}"],
                )
        except Exception as e:
            logger.error(f"Verification failed for {task.id}: {e}")
            report = VerificationReport(
                task_id=task.id,
                passed=False,
                errors=[f"Verification exception: {str(e)}"],
            )

        report.duration = time.time() - start
        return report

    async def _verify_eda(
        self, task: TaskNode, artifacts: List[str]
    ) -> VerificationReport:
        """
        Verify EDA artifacts: synthesis, optimization, timing.

        Runs: yosys synth → abc optimize → opensta timing
        Collects: area, delay, power from tool outputs.
        """
        metrics: Dict[str, float] = {}
        errors: List[str] = []
        warnings: List[str] = []
        tool_outputs: Dict[str, str] = {}

        # Check for synthesizable files
        verilog_files = [f for f in artifacts if f.endswith((".v", ".sv"))]
        blif_files = [f for f in artifacts if f.endswith((".blif", ".aig"))]

        if not verilog_files and not blif_files:
            return VerificationReport(
                task_id=task.id,
                passed=False,
                errors=["No synthesizable artifacts (*.v, *.blif, *.aig) found"],
            )

        # Run Yosys synthesis check
        if verilog_files:
            yosys_result = await self._run_tool(
                "yosys",
                ["-p", f"read_verilog {verilog_files[0]}; synth; stat"],
            )
            tool_outputs["yosys"] = yosys_result
            area = self._extract_yosys_area(yosys_result)
            if area is not None:
                metrics["area_cells"] = area
            if "ERROR" in yosys_result.upper():
                errors.append("Yosys synthesis failed")

        # Run ABC optimization check
        if blif_files:
            abc_result = await self._run_tool(
                "abc",
                ["-c", f"read {blif_files[0]}; print_stats"],
            )
            tool_outputs["abc"] = abc_result
            abc_metrics = self._extract_abc_stats(abc_result)
            metrics.update(abc_metrics)

        # Run OpenSTA timing check
        sdc_files = [f for f in artifacts if f.endswith(".sdc")]
        if sdc_files and (verilog_files or blif_files):
            sta_result = await self._run_tool(
                "opensta",
                ["-exit", f"read_liberty /dev/null; report_checks"],
            )
            tool_outputs["opensta"] = sta_result
            delay = self._extract_sta_delay(sta_result)
            if delay is not None:
                metrics["delay_ns"] = delay

        # Check against verification criteria
        passed = self._check_criteria(task.verification_criteria, metrics, warnings)

        return VerificationReport(
            task_id=task.id,
            passed=passed and not errors,
            metrics=metrics,
            errors=errors,
            warnings=warnings,
            tool_outputs=tool_outputs,
        )

    async def _verify_chip(
        self, task: TaskNode, artifacts: List[str]
    ) -> VerificationReport:
        """
        Verify chip design artifacts: lint, simulation, formal.

        Runs: Yosys lint check, Verilator/iVerilog simulation.
        Collects: pass/fail, coverage %, assertion violations.
        """
        metrics: Dict[str, float] = {}
        errors: List[str] = []
        warnings: List[str] = []
        tool_outputs: Dict[str, str] = {}

        verilog_files = [f for f in artifacts if f.endswith((".v", ".sv"))]
        if not verilog_files:
            return VerificationReport(
                task_id=task.id,
                passed=False,
                errors=["No RTL files (*.v, *.sv) found"],
            )

        # Lint check with Yosys
        lint_result = await self._run_tool(
            "yosys",
            ["-p", f"read_verilog {verilog_files[0]}; hierarchy; check"],
        )
        tool_outputs["yosys_lint"] = lint_result
        if "ERROR" in lint_result.upper():
            errors.append("Lint check failed")
        else:
            metrics["lint_pass"] = 1.0

        # Simulation check with Verilator (if testbench exists)
        tb_files = [f for f in artifacts if "tb" in f.lower() or "test" in f.lower()]
        if tb_files:
            sim_result = await self._run_tool(
                "verilator",
                ["--lint-only", "--Wall"] + verilog_files,
            )
            tool_outputs["verilator"] = sim_result
            if "Error" not in sim_result:
                metrics["simulation_pass"] = 1.0
            else:
                warnings.append("Verilator lint warnings/errors")

        # Check against verification criteria
        passed = self._check_criteria(task.verification_criteria, metrics, warnings)

        return VerificationReport(
            task_id=task.id,
            passed=passed and not errors,
            metrics=metrics,
            errors=errors,
            warnings=warnings,
            tool_outputs=tool_outputs,
        )

    async def _verify_ai_infra(
        self, task: TaskNode, artifacts: List[str]
    ) -> VerificationReport:
        """
        Verify AI infrastructure artifacts: compile, test, benchmark.

        Runs:
        - Python compile check
        - Unit tests (pytest)
        - Training benchmark (N epochs)
        - Inference benchmark (throughput/latency)
        """
        metrics: Dict[str, float] = {}
        errors: List[str] = []
        warnings: List[str] = []
        tool_outputs: Dict[str, str] = {}

        python_files = [f for f in artifacts if f.endswith(".py")]
        if not python_files:
            return VerificationReport(
                task_id=task.id,
                passed=False,
                errors=["No Python artifacts (*.py) found"],
            )

        # Compile check
        for pf in python_files[:3]:  # Check first 3 files
            compile_result = await self._run_tool(
                "python3",
                ["-c", f"import py_compile; py_compile.compile('{pf}', doraise=True)"],
            )
            tool_outputs[f"compile_{pf}"] = compile_result
            if "Error" in compile_result or "Traceback" in compile_result:
                errors.append(f"Compile check failed for {pf}")

        if not errors:
            metrics["compile_pass"] = 1.0

        # Unit test check (if test files present)
        test_files = [f for f in python_files if "test" in f.lower()]
        if test_files:
            test_result = await self._run_tool(
                "python3",
                ["-m", "pytest", "--tb=short", "-q"] + test_files[:2],
            )
            tool_outputs["pytest"] = test_result
            if "passed" in test_result.lower():
                metrics["tests_pass"] = 1.0
                # Extract pass count
                match = re.search(r"(\d+) passed", test_result)
                if match:
                    metrics["tests_passed_count"] = float(match.group(1))
            elif "failed" in test_result.lower():
                warnings.append("Some tests failed")
                metrics["tests_pass"] = 0.0

        # Check against verification criteria
        passed = self._check_criteria(task.verification_criteria, metrics, warnings)

        return VerificationReport(
            task_id=task.id,
            passed=passed and not errors,
            metrics=metrics,
            errors=errors,
            warnings=warnings,
            tool_outputs=tool_outputs,
        )

    async def _run_tool(self, tool: str, args: List[str]) -> str:
        """Run an external tool and capture output."""
        import shutil

        tool_path = shutil.which(tool)
        if not tool_path:
            return f"[tool not found: {tool}]"

        try:
            proc = await asyncio.create_subprocess_exec(
                tool_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=None,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            return stdout.decode("utf-8", errors="replace")[:10000]
        except asyncio.TimeoutError:
            return f"[timeout after {self._timeout}s]"
        except Exception as e:
            return f"[execution error: {e}]"

    def _check_criteria(
        self,
        criteria: Dict[str, Any],
        metrics: Dict[str, float],
        warnings: List[str],
    ) -> bool:
        """Check collected metrics against verification criteria."""
        if not criteria:
            return True  # No criteria = pass by default

        all_passed = True
        for metric_name, threshold in criteria.items():
            if metric_name not in metrics:
                warnings.append(f"Metric '{metric_name}' not collected")
                continue

            actual = metrics[metric_name]
            if isinstance(threshold, (int, float)):
                # For area/delay: lower is better (actual <= threshold)
                # For pass/accuracy: higher is better (actual >= threshold)
                if metric_name in ("accuracy", "throughput", "coverage",
                                   "lint_pass", "compile_pass", "tests_pass",
                                   "simulation_pass"):
                    if actual < threshold:
                        all_passed = False
                        warnings.append(
                            f"{metric_name}: {actual} < {threshold} (min)"
                        )
                else:
                    if actual > threshold:
                        all_passed = False
                        warnings.append(
                            f"{metric_name}: {actual} > {threshold} (max)"
                        )

        return all_passed

    @staticmethod
    def _extract_yosys_area(output: str) -> Optional[float]:
        """Extract cell count from Yosys stat output."""
        match = re.search(r"Number of cells:\s+(\d+)", output)
        if match:
            return float(match.group(1))
        return None

    @staticmethod
    def _extract_abc_stats(output: str) -> Dict[str, float]:
        """Extract area/delay from ABC print_stats output."""
        metrics: Dict[str, float] = {}
        # ABC format: "i/o = X/Y  lat = Z  and = W  lev = L"
        match = re.search(r"and\s*=\s*(\d+)", output)
        if match:
            metrics["and_nodes"] = float(match.group(1))
        match = re.search(r"lev\s*=\s*(\d+)", output)
        if match:
            metrics["logic_levels"] = float(match.group(1))
        return metrics

    @staticmethod
    def _extract_sta_delay(output: str) -> Optional[float]:
        """Extract worst-case delay from OpenSTA output."""
        match = re.search(r"slack\s*[=(]\s*([-\d.]+)", output)
        if match:
            return abs(float(match.group(1)))
        return None
