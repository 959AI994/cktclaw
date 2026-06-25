"""
System Loop Controller — main orchestrator for the 4-phase closed loop.

Drives the DEFINE → GENERATE → VERIFY → EVOLVE cycle until convergence,
budget exhaustion, or stuck detection.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_graph import CrossLayerTaskGraph, TaskNode
from .goal_decomposer import GoalDecomposer
from .domain_teams import DomainTeam, EDATeam, ChipTeam, AIInfraTeam, TaskResult
from .verification import VerificationRunner, VerificationReport
from .evolution import EvolutionEngine

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    """Configuration for the system loop."""

    max_iterations: int = 10
    convergence_threshold: float = 0.02  # 2% improvement minimum
    timeout_seconds: int = 3600  # 1 hour total
    domains: List[str] = field(default_factory=lambda: ["eda", "chip", "ai_infra"])
    parallel_tasks: bool = True  # Execute ready tasks in parallel


@dataclass
class LoopResult:
    """Final result of a system loop run."""

    session_id: str
    goal: str
    status: str  # "converged" | "stuck" | "timeout" | "max_iterations" | "error"
    iterations_completed: int
    total_tasks: int
    passed_tasks: int
    failed_tasks: int
    final_graph: Optional[Dict[str, Any]] = None
    metrics_history: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "iterations_completed": self.iterations_completed,
            "total_tasks": self.total_tasks,
            "passed_tasks": self.passed_tasks,
            "failed_tasks": self.failed_tasks,
            "duration_seconds": self.duration_seconds,
            "artifacts": self.artifacts,
            "metrics_history": self.metrics_history,
        }

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.passed_tasks / self.total_tasks


class SystemLoopController:
    """
    Main orchestrator for the cross-domain system closed loop.

    Phases:
    1. DEFINE:   Decompose goal into CrossLayerTaskGraph
    2. GENERATE: Domain teams execute ready tasks in parallel
    3. VERIFY:   Run real tool chains, collect metrics
    4. EVOLVE:   Analyze bottlenecks, generate feedback, check convergence
    """

    def __init__(self, config: Optional[LoopConfig] = None, llm_func=None):
        self.config = config or LoopConfig()
        self.decomposer = GoalDecomposer(llm_func=llm_func)
        self.teams: Dict[str, DomainTeam] = {
            "eda": EDATeam(),
            "chip": ChipTeam(),
            "ai_infra": AIInfraTeam(),
        }
        self.verifier = VerificationRunner()
        self.evolution = EvolutionEngine(
            llm_func=llm_func,
            convergence_threshold=self.config.convergence_threshold,
        )
        self._trajectory = None
        self._init_trajectory()

    def _init_trajectory(self) -> None:
        """Initialize trajectory logger."""
        try:
            from ..trajectory import get_trajectory_logger
            self._trajectory = get_trajectory_logger()
        except Exception:
            pass

    async def run(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> LoopResult:
        """
        Execute the full system loop.

        Args:
            goal: High-level system objective.
            constraints: Optional constraints dict.

        Returns:
            LoopResult with final status and collected artifacts.
        """
        session_id = f"loop_{uuid.uuid4().hex[:8]}"
        start_time = time.time()
        constraints = constraints or {}

        self._log_event(session_id, "loop_started", {"goal": goal})

        # Phase 1: DEFINE — Decompose goal into task graph
        logger.info(f"[{session_id}] Phase 1: DEFINE — decomposing goal")
        try:
            graph = await self.decomposer.decompose(goal, constraints)
        except Exception as e:
            logger.error(f"Goal decomposition failed: {e}")
            return LoopResult(
                session_id=session_id,
                goal=goal,
                status="error",
                iterations_completed=0,
                total_tasks=0,
                passed_tasks=0,
                failed_tasks=0,
                duration_seconds=time.time() - start_time,
            )

        if len(graph) == 0:
            logger.warning("Goal decomposition produced empty graph")
            return LoopResult(
                session_id=session_id,
                goal=goal,
                status="error",
                iterations_completed=0,
                total_tasks=0,
                passed_tasks=0,
                failed_tasks=0,
                duration_seconds=time.time() - start_time,
            )

        self._log_event(session_id, "graph_created", {
            "task_count": len(graph),
            "domains": list(set(t.domain for t in graph.get_all_tasks())),
        })

        # Main loop: GENERATE → VERIFY → EVOLVE
        status = "max_iterations"
        for iteration in range(self.config.max_iterations):
            elapsed = time.time() - start_time
            if elapsed > self.config.timeout_seconds:
                status = "timeout"
                break

            logger.info(
                f"[{session_id}] Iteration {iteration + 1}/{self.config.max_iterations}"
            )
            self._log_event(session_id, "iteration_start", {"iteration": iteration})

            # Phase 2: GENERATE — execute ready tasks in parallel
            ready_tasks = graph.get_ready_tasks()
            if not ready_tasks:
                # No ready tasks — check if we're done or stuck
                all_tasks = graph.get_all_tasks()
                if all(t.status == "passed" for t in all_tasks):
                    status = "converged"
                    break
                elif graph.get_blocked_tasks():
                    # Reset blocked/failed for retry
                    graph.reset_failed_tasks(iteration)
                    ready_tasks = graph.get_ready_tasks()
                    if not ready_tasks:
                        status = "stuck"
                        break
                else:
                    status = "stuck"
                    break

            # Execute tasks
            results = await self._execute_tasks(ready_tasks, iteration)

            # Phase 3: VERIFY — run tool chains
            reports = await self._verify_tasks(ready_tasks, results)

            # Update graph with results
            for task, report in zip(ready_tasks, reports):
                task_status = "passed" if report.passed else "failed"
                graph.complete_task(
                    task.id,
                    status=task_status,
                    metrics=report.metrics,
                    artifacts=task.artifacts,
                )

            # Phase 4: EVOLVE — analyze + feedback + convergence check
            decision = await self.evolution.step(graph, reports, iteration)

            self._log_event(session_id, "iteration_end", {
                "iteration": iteration,
                "decision": decision,
                "ready_count": len(ready_tasks),
                "passed": sum(1 for r in reports if r.passed),
                "failed": sum(1 for r in reports if not r.passed),
            })

            if decision == "converged":
                status = "converged"
                break
            elif decision == "stuck":
                # Try one more time with feedback
                feedback = await self.evolution.get_feedback(graph, reports)
                graph.reset_failed_tasks(iteration + 1)
                logger.info(f"[{session_id}] Feedback generated: {list(feedback.keys())}")
            elif decision == "pivot":
                # Re-decompose with learnings
                logger.info(f"[{session_id}] Pivoting — re-decomposing with experience")
                graph.reset_failed_tasks(iteration + 1)

        # Build final result
        all_tasks = graph.get_all_tasks()
        all_artifacts = []
        for t in all_tasks:
            all_artifacts.extend(t.artifacts)

        result = LoopResult(
            session_id=session_id,
            goal=goal,
            status=status,
            iterations_completed=min(
                iteration + 1 if 'iteration' in dir() else 0,
                self.config.max_iterations,
            ),
            total_tasks=len(all_tasks),
            passed_tasks=sum(1 for t in all_tasks if t.status == "passed"),
            failed_tasks=sum(1 for t in all_tasks if t.status == "failed"),
            final_graph=graph.to_dict(),
            metrics_history=self.evolution.get_iteration_history(),
            duration_seconds=time.time() - start_time,
            artifacts=all_artifacts,
        )

        self._log_event(session_id, "loop_finished", result.to_dict())
        return result

    async def _execute_tasks(
        self, tasks: List[TaskNode], iteration: int
    ) -> List[TaskResult]:
        """Execute tasks using domain teams."""
        if self.config.parallel_tasks:
            # Parallel execution across domains
            coros = []
            for task in tasks:
                task.status = "running"
                task.iteration = iteration
                team = self.teams.get(task.domain)
                if team:
                    experience = self.evolution.get_experience(task)
                    coros.append(team.execute_task(task, experience))
                else:
                    # Fallback: return empty result
                    async def _noop(t=task):
                        return TaskResult(task_id=t.id, success=False, error="No team")
                    coros.append(_noop())

            results = await asyncio.gather(*coros, return_exceptions=True)
            # Convert exceptions to failed results
            cleaned: List[TaskResult] = []
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    cleaned.append(TaskResult(
                        task_id=tasks[i].id,
                        success=False,
                        error=str(r),
                    ))
                else:
                    cleaned.append(r)
            return cleaned
        else:
            # Sequential execution
            results: List[TaskResult] = []
            for task in tasks:
                task.status = "running"
                task.iteration = iteration
                team = self.teams.get(task.domain)
                if team:
                    experience = self.evolution.get_experience(task)
                    result = await team.execute_task(task, experience)
                    results.append(result)
                else:
                    results.append(TaskResult(
                        task_id=task.id, success=False, error="No team"
                    ))
            return results

    async def _verify_tasks(
        self, tasks: List[TaskNode], results: List[TaskResult]
    ) -> List[VerificationReport]:
        """Verify all task results."""
        coros = []
        for task, result in zip(tasks, results):
            # Merge result artifacts into task
            task.artifacts = result.artifacts
            coros.append(self.verifier.verify_task(task, result.artifacts))

        reports = await asyncio.gather(*coros, return_exceptions=True)
        cleaned: List[VerificationReport] = []
        for i, r in enumerate(reports):
            if isinstance(r, Exception):
                cleaned.append(VerificationReport(
                    task_id=tasks[i].id,
                    passed=False,
                    errors=[str(r)],
                ))
            else:
                cleaned.append(r)
        return cleaned

    def _log_event(self, session_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Log an event to the trajectory logger."""
        if self._trajectory:
            self._trajectory._write_event(session_id, f"loop_{event_type}", data)
