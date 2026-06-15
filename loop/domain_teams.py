"""
Domain Agent Teams — wraps existing agent infrastructure into three
specialized teams: EDA, Chip, and AI Infrastructure.

Each team coordinates its domain-specific agents to execute tasks
from the CrossLayerTaskGraph.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_graph import TaskNode

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of a domain team executing a task."""

    task_id: str
    success: bool
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    output: str = ""
    error: str = ""


class DomainTeam(ABC):
    """
    Base class for domain-specific agent teams.

    Each team wraps a set of specialized agents and orchestrators
    to execute tasks within their domain.
    """

    domain: str = "base"

    def __init__(self):
        self._execution_count = 0

    async def execute_task(
        self,
        task: TaskNode,
        experience: Optional[List[Any]] = None,
    ) -> TaskResult:
        """
        Execute a task using domain-specific agents.

        Args:
            task: The task node to execute.
            experience: Previous experience records for context.

        Returns:
            TaskResult with artifacts and metrics.
        """
        self._execution_count += 1
        experience = experience or []

        context = self._build_context(task, experience)
        agents = self._select_agents(task)

        logger.info(
            f"[{self.domain}] Executing task {task.id}: {task.description[:80]}..."
        )
        logger.debug(f"[{self.domain}] Selected agents: {agents}")

        try:
            result = await self._run_agents(task, agents, context)
            return result
        except Exception as e:
            logger.error(f"[{self.domain}] Task {task.id} failed: {e}")
            return TaskResult(
                task_id=task.id,
                success=False,
                error=str(e),
            )

    @abstractmethod
    def _select_agents(self, task: TaskNode) -> List[str]:
        """Select which agents/skills to use for this task."""
        ...

    def _build_context(self, task: TaskNode, experience: List[Any]) -> str:
        """Build execution context from task + experience."""
        parts = [
            f"## Task: {task.description}",
            f"Domain: {task.domain}",
            f"Type: {task.task_type}",
            f"Verification Criteria: {task.verification_criteria}",
        ]
        if task.dependencies:
            parts.append(f"Dependencies: {task.dependencies}")
        if experience:
            parts.append("\n## Relevant Experience:")
            for exp in experience[:5]:
                if hasattr(exp, "lesson"):
                    parts.append(f"- {exp.lesson}")
                elif isinstance(exp, dict):
                    parts.append(f"- {exp.get('lesson', str(exp))}")
        return "\n".join(parts)

    @abstractmethod
    async def _run_agents(
        self, task: TaskNode, agents: List[str], context: str
    ) -> TaskResult:
        """Run the selected agents to execute the task."""
        ...


class EDATeam(DomainTeam):
    """
    EDA domain team — synthesis, PnR, timing, power.

    Reuses:
    - OrchestratorEngine for multi-stage EDA flows
    - RLTFCoordinator for optimization sub-tasks
    - NegotiationCoordinator for PPA trade-off tasks
    """

    domain = "eda"

    def _select_agents(self, task: TaskNode) -> List[str]:
        """Select EDA agents based on task description."""
        desc = task.description.lower()
        agents = []

        if any(k in desc for k in ("synth", "synthesis", "logic")):
            agents.append("chip-synthesis")
        if any(k in desc for k in ("place", "route", "pnr", "floorplan")):
            agents.append("chip-pnr")
        if any(k in desc for k in ("timing", "sta", "delay", "slack")):
            agents.append("chip-sta")
        if any(k in desc for k in ("power", "leakage", "dynamic")):
            agents.append("chip-signoff")
        if any(k in desc for k in ("optim", "rltf", "abc")):
            agents.append("rltf")
        if any(k in desc for k in ("pareto", "trade-off", "negotiate")):
            agents.append("pareto-negotiate")

        return agents or ["chip-synthesis"]

    async def _run_agents(
        self, task: TaskNode, agents: List[str], context: str
    ) -> TaskResult:
        """Execute EDA task using WorkerAgent with EDA tools."""
        from ..agents.runtime import get_agent_runtime
        from ..agents.base import AgentBudget

        runtime = get_agent_runtime()
        system_prompt = (
            "You are a CktClaw EDA specialist agent. "
            "Execute the given EDA task using available synthesis, "
            "optimization, and analysis tools.\n\n"
            f"{context}"
        )

        agent_id = await runtime.spawn_worker(
            name=f"eda_{task.id}",
            task=task.description,
            system_prompt=system_prompt,
            allowed_tools=["yosys", "abc", "opensta", "openroad", "bash_tool", "file_tool"],
            budget=AgentBudget(max_turns=15, timeout_seconds=600),
        )

        result_text = await runtime.wait_for(agent_id, timeout=600)
        status = runtime.get_status(agent_id)

        return TaskResult(
            task_id=task.id,
            success=status.get("status") == "completed" if status else False,
            output=result_text or "",
            artifacts=self._extract_artifacts(result_text or ""),
        )

    @staticmethod
    def _extract_artifacts(output: str) -> List[str]:
        """Extract file paths from agent output."""
        import re
        paths = re.findall(r'(?:^|\s)(/[^\s]+\.(?:v|blif|aig|sdc|def|lef|lib))', output)
        return paths


class ChipTeam(DomainTeam):
    """
    Chip design team — architecture, RTL, verification.

    Reuses:
    - chip-architecture, chip-rtl, chip-verification orchestrators
    - Verilator/iVerilog for simulation
    """

    domain = "chip"

    def _select_agents(self, task: TaskNode) -> List[str]:
        """Select chip design agents based on task description."""
        desc = task.description.lower()
        agents = []

        if any(k in desc for k in ("arch", "microarch", "design space")):
            agents.append("chip-architecture")
        if any(k in desc for k in ("rtl", "verilog", "hdl", "module")):
            agents.append("chip-rtl")
        if any(k in desc for k in ("verif", "testbench", "simulation", "assert")):
            agents.append("chip-verification")
        if any(k in desc for k in ("dft", "scan", "bist")):
            agents.append("chip-dft")
        if any(k in desc for k in ("constraint", "sdc", "clock")):
            agents.append("chip-constraints")

        return agents or ["chip-rtl"]

    async def _run_agents(
        self, task: TaskNode, agents: List[str], context: str
    ) -> TaskResult:
        """Execute chip design task using WorkerAgent."""
        from ..agents.runtime import get_agent_runtime
        from ..agents.base import AgentBudget

        runtime = get_agent_runtime()
        system_prompt = (
            "You are a CktClaw chip design specialist agent. "
            "Execute the given chip design task — architecture, RTL, "
            "or verification — using available tools.\n\n"
            f"{context}"
        )

        agent_id = await runtime.spawn_worker(
            name=f"chip_{task.id}",
            task=task.description,
            system_prompt=system_prompt,
            allowed_tools=["yosys", "bash_tool", "file_tool", "verilator"],
            budget=AgentBudget(max_turns=15, timeout_seconds=600),
        )

        result_text = await runtime.wait_for(agent_id, timeout=600)
        status = runtime.get_status(agent_id)

        return TaskResult(
            task_id=task.id,
            success=status.get("status") == "completed" if status else False,
            output=result_text or "",
            artifacts=self._extract_artifacts(result_text or ""),
        )

    @staticmethod
    def _extract_artifacts(output: str) -> List[str]:
        """Extract file paths from agent output."""
        import re
        paths = re.findall(r'(?:^|\s)(/[^\s]+\.(?:v|sv|vh|svh|vcd|fst))', output)
        return paths


class AIInfraTeam(DomainTeam):
    """
    AI Infrastructure team — training, inference, compiler, deployment.

    Generates:
    - PyTorch training scripts + data pipelines
    - TVM/MLIR compiler optimization passes
    - Inference engine code (quantization, graph optimization)
    - Hardware deployment scripts
    """

    domain = "ai_infra"

    def _select_agents(self, task: TaskNode) -> List[str]:
        """Select AI infrastructure agents based on task description."""
        desc = task.description.lower()
        agents = []

        if any(k in desc for k in ("train", "dataset", "dataloader", "epoch")):
            agents.append("ai-training")
        if any(k in desc for k in ("infer", "deploy", "serving", "throughput")):
            agents.append("ai-inference")
        if any(k in desc for k in ("compil", "tvm", "mlir", "kernel", "codegen")):
            agents.append("ai-compiler")
        if any(k in desc for k in ("quant", "prune", "distill", "compress")):
            agents.append("ai-optimization")
        if any(k in desc for k in ("fpga", "bitstream", "asic", "hardware")):
            agents.append("ai-hw-deploy")

        return agents or ["ai-training"]

    async def _run_agents(
        self, task: TaskNode, agents: List[str], context: str
    ) -> TaskResult:
        """Execute AI infrastructure task using WorkerAgent with code gen."""
        from ..agents.runtime import get_agent_runtime
        from ..agents.base import AgentBudget

        runtime = get_agent_runtime()
        system_prompt = (
            "You are a CktClaw AI infrastructure specialist agent. "
            "Execute the given task: generate training scripts, "
            "compiler passes, inference code, or deployment configs.\n\n"
            "When generating code:\n"
            "1. Write complete, runnable Python files\n"
            "2. Include proper imports and error handling\n"
            "3. Add brief inline comments for complex logic\n"
            "4. Target PyTorch for training, TVM for compilation\n\n"
            f"{context}"
        )

        agent_id = await runtime.spawn_worker(
            name=f"ai_{task.id}",
            task=task.description,
            system_prompt=system_prompt,
            allowed_tools=["bash_tool", "file_tool", "python_tool"],
            budget=AgentBudget(max_turns=20, timeout_seconds=900),
        )

        result_text = await runtime.wait_for(agent_id, timeout=900)
        status = runtime.get_status(agent_id)

        return TaskResult(
            task_id=task.id,
            success=status.get("status") == "completed" if status else False,
            output=result_text or "",
            artifacts=self._extract_artifacts(result_text or ""),
        )

    @staticmethod
    def _extract_artifacts(output: str) -> List[str]:
        """Extract file paths from agent output."""
        import re
        paths = re.findall(
            r'(?:^|\s)(/[^\s]+\.(?:py|onnx|pt|pth|tflite|so|json|yaml))', output
        )
        return paths
