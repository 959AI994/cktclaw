"""
Goal Decomposer — breaks high-level system objectives into a CrossLayerTaskGraph.

Uses LLM to decompose a goal like "design a low-power CNN accelerator and
generate its training framework" into a DAG of verifiable cross-domain tasks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .task_graph import CrossLayerTaskGraph, TaskNode

logger = logging.getLogger(__name__)

# Domain vocabulary used in the decomposition prompt
DOMAIN_VOCABULARY = {
    "eda": [
        "synthesis", "placement", "routing", "timing_analysis",
        "power_analysis", "clock_tree_synthesis", "floorplanning",
        "logic_optimization", "technology_mapping",
    ],
    "chip": [
        "architecture_exploration", "rtl_coding", "functional_verification",
        "dft_insertion", "constraint_definition", "ip_integration",
        "microarchitecture_design", "bus_protocol", "register_file",
    ],
    "ai_infra": [
        "operator_implementation", "compiler_passes", "training_scripts",
        "inference_optimization", "quantization", "data_pipeline",
        "model_architecture", "hardware_mapping", "kernel_tuning",
    ],
}

DECOMPOSITION_PROMPT_TEMPLATE = """You are a cross-domain system architect. Decompose the following high-level goal into a task graph spanning EDA, chip design, and AI infrastructure.

## Goal
{goal}

## Constraints
{constraints}

## Available Domains and Capabilities

### EDA Domain
Capabilities: {eda_capabilities}
Tools: Yosys (synthesis), ABC (logic optimization), OpenSTA (timing), OpenROAD (PnR)

### Chip Domain
Capabilities: {chip_capabilities}
Tools: Verilator (simulation), Yosys (lint), formal verification

### AI Infrastructure Domain
Capabilities: {ai_capabilities}
Tools: PyTorch, TVM/MLIR compiler, inference engines

## Output Format
Return a JSON object with a "tasks" array. Each task has:
- "id": unique string identifier (e.g., "eda_synth_1", "chip_rtl_1", "ai_train_1")
- "domain": one of "eda", "chip", "ai_infra"
- "task_type": one of "generate", "verify", "analyze"
- "description": clear actionable description
- "dependencies": list of task IDs this depends on (empty list if none)
- "verification_criteria": dict of metric_name -> threshold (e.g., {{"area_um2": 50000, "delay_ns": 2.0}})

## Rules
1. Tasks must form a valid DAG (no cycles)
2. Cross-domain dependencies are encouraged (e.g., AI training depends on chip RTL for hardware-aware optimization)
3. Each task must have clear verification criteria
4. Aim for 5-15 tasks total
5. Include at least one task per domain if the goal spans multiple domains

Return ONLY the JSON object, no other text.
"""


class GoalDecomposer:
    """
    Decomposes a high-level system objective into a CrossLayerTaskGraph.

    Uses LLM-based reasoning to:
    1. Identify sub-tasks across EDA, chip, and AI domains
    2. Establish dependencies between tasks
    3. Define verification criteria for each task
    """

    def __init__(self, llm_func=None):
        """
        Args:
            llm_func: Async callable(prompt: str) -> str.
                      If None, uses the default LLM router.
        """
        self._llm_func = llm_func

    async def decompose(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> CrossLayerTaskGraph:
        """
        Decompose a goal into a task graph.

        Args:
            goal: High-level system objective.
            constraints: Optional constraints (budget, timeline, tech node, etc.)

        Returns:
            CrossLayerTaskGraph with all tasks and dependencies.
        """
        constraints = constraints or {}
        prompt = self._build_decomposition_prompt(goal, constraints)
        llm_output = await self._call_llm(prompt)
        graph = self._parse_task_graph(llm_output)
        warnings = self._validate_graph(graph)
        if warnings:
            logger.warning(f"Graph validation warnings: {warnings}")
        return graph

    def _build_decomposition_prompt(
        self, goal: str, constraints: Dict[str, Any]
    ) -> str:
        """Build the LLM prompt for decomposition."""
        constraints_str = json.dumps(constraints, indent=2) if constraints else "None"
        return DECOMPOSITION_PROMPT_TEMPLATE.format(
            goal=goal,
            constraints=constraints_str,
            eda_capabilities=", ".join(DOMAIN_VOCABULARY["eda"]),
            chip_capabilities=", ".join(DOMAIN_VOCABULARY["chip"]),
            ai_capabilities=", ".join(DOMAIN_VOCABULARY["ai_infra"]),
        )

    def _parse_task_graph(self, llm_output: str) -> CrossLayerTaskGraph:
        """Parse LLM output JSON into a CrossLayerTaskGraph."""
        graph = CrossLayerTaskGraph()

        # Try to extract JSON from the output
        json_str = self._extract_json(llm_output)
        if not json_str:
            logger.error("Failed to extract JSON from LLM output")
            return graph

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return graph

        tasks_data = data.get("tasks", [])
        if not isinstance(tasks_data, list):
            logger.error("'tasks' field is not a list")
            return graph

        for task_data in tasks_data:
            node = TaskNode(
                id=task_data.get("id", ""),
                domain=self._normalize_domain(task_data.get("domain", "eda")),
                task_type=self._normalize_task_type(task_data.get("task_type", "generate")),
                description=task_data.get("description", ""),
                dependencies=task_data.get("dependencies", []),
                verification_criteria=task_data.get("verification_criteria", {}),
                status="pending",
            )
            if node.id:
                graph.add_task(node)

        return graph

    def _validate_graph(self, graph: CrossLayerTaskGraph) -> List[str]:
        """Validate the graph structure. Returns list of warnings."""
        warnings: List[str] = []

        if len(graph) == 0:
            warnings.append("Graph is empty")
            return warnings

        # Check for missing dependency references
        all_ids = set(graph.nodes.keys())
        for node in graph.get_all_tasks():
            for dep_id in node.dependencies:
                if dep_id not in all_ids:
                    warnings.append(
                        f"Task {node.id} depends on non-existent task {dep_id}"
                    )

        # Check for cycles (DFS)
        if self._has_cycle(graph):
            warnings.append("Graph contains a cycle — breaking circular dependencies")

        # Check for tasks without verification criteria
        for node in graph.get_all_tasks():
            if not node.verification_criteria:
                warnings.append(f"Task {node.id} has no verification criteria")

        return warnings

    def _has_cycle(self, graph: CrossLayerTaskGraph) -> bool:
        """Detect cycles using DFS coloring."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in graph.nodes}

        def dfs(nid: str) -> bool:
            color[nid] = GRAY
            node = graph.get_task(nid)
            if node:
                # Check successors (nodes that depend on this one)
                for other in graph.get_all_tasks():
                    if nid in other.dependencies:
                        if color.get(other.id) == GRAY:
                            return True
                        if color.get(other.id) == WHITE:
                            if dfs(other.id):
                                return True
            color[nid] = BLACK
            return False

        for nid in list(graph.nodes.keys()):
            if color[nid] == WHITE:
                if dfs(nid):
                    return True
        return False

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM to get decomposition."""
        if self._llm_func:
            return await self._llm_func(prompt)

        # Default: use the model router
        try:
            from ..llm import get_model_router
            router = get_model_router()
            provider = router.current_provider
            if provider:
                from ..llm.base import ChatMessage
                from ..llm.types import MessageRole
                messages = [
                    ChatMessage(role=MessageRole.USER, content=prompt)
                ]
                response = await provider.chat(messages=messages, temperature=0.2)
                return response.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
        return ""

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """Extract JSON from text, handling markdown code blocks."""
        import re

        # Try to find ```json ... ``` block
        match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        # Try to find raw JSON object
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        return None

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Normalize domain string to valid literal."""
        domain = domain.lower().strip()
        valid = ("eda", "chip", "ai_infra")
        if domain in valid:
            return domain
        # Fuzzy match
        if "eda" in domain or "synth" in domain or "route" in domain:
            return "eda"
        if "chip" in domain or "rtl" in domain or "arch" in domain:
            return "chip"
        if "ai" in domain or "train" in domain or "infra" in domain:
            return "ai_infra"
        return "eda"

    @staticmethod
    def _normalize_task_type(task_type: str) -> str:
        """Normalize task_type string to valid literal."""
        task_type = task_type.lower().strip()
        valid = ("generate", "verify", "analyze")
        if task_type in valid:
            return task_type
        if "gen" in task_type or "create" in task_type or "build" in task_type:
            return "generate"
        if "verif" in task_type or "test" in task_type or "check" in task_type:
            return "verify"
        return "analyze"
