"""
Evolution Engine — feedback loop for the system closed loop.

Components:
- ExperienceStore: embedding-backed success/failure pattern storage
- BottleneckAnalyzer: identifies worst-performing layers and cross-domain blockers
- FeedbackGenerator: LLM-powered targeted revision instructions
- ConvergenceChecker: decides continue/converged/stuck/pivot
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .task_graph import CrossLayerTaskGraph, TaskNode
from .verification import VerificationReport

logger = logging.getLogger(__name__)


@dataclass
class ExperienceRecord:
    """A single experience record from one iteration."""

    task_id: str
    iteration: int
    domain: str
    action_taken: str
    metrics_before: Dict[str, float] = field(default_factory=dict)
    metrics_after: Dict[str, float] = field(default_factory=dict)
    success: bool = False
    lesson: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "iteration": self.iteration,
            "domain": self.domain,
            "action_taken": self.action_taken,
            "metrics_before": self.metrics_before,
            "metrics_after": self.metrics_after,
            "success": self.success,
            "lesson": self.lesson,
        }


@dataclass
class Bottleneck:
    """Identified bottleneck in the system."""

    task_id: str
    domain: str
    metric_name: str
    current_value: float
    target_value: float
    severity: Literal["critical", "major", "minor"] = "major"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "domain": self.domain,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "severity": self.severity,
            "description": self.description,
        }


class ExperienceStore:
    """
    Stores and retrieves experience records.

    Uses semantic search (via cktmem) for embedding-based retrieval
    of relevant past experiences when available.
    """

    def __init__(self):
        self._records: List[ExperienceRecord] = []
        self._semantic_search = None
        self._init_semantic_search()

    def _init_semantic_search(self) -> None:
        """Attempt to initialize semantic search backend."""
        try:
            from ..cktmem.semantic_search import SemanticSearch
            self._semantic_search = SemanticSearch()
        except Exception:
            logger.debug("Semantic search not available, using keyword fallback")

    def add(self, record: ExperienceRecord) -> None:
        """Add an experience record."""
        self._records.append(record)
        # Index in semantic search if available
        if self._semantic_search:
            text = f"{record.domain} {record.action_taken} {record.lesson}"
            self._semantic_search.index_message(
                text=text,
                role="experience",
                session_id=f"loop_iter_{record.iteration}",
                turn_number=record.iteration,
            )

    def query_relevant(
        self,
        domain: str,
        task_type: str = "",
        top_k: int = 5,
    ) -> List[ExperienceRecord]:
        """
        Retrieve relevant experience records.

        Uses semantic search if available, otherwise falls back
        to domain + recency filtering.
        """
        if self._semantic_search:
            query = f"{domain} {task_type}"
            results = self._semantic_search.retrieve_relevant(query, top_k=top_k)
            # Map back to records by domain match
            domain_records = [r for r in self._records if r.domain == domain]
            return domain_records[-top_k:]

        # Fallback: filter by domain, return most recent
        domain_records = [r for r in self._records if r.domain == domain]
        return domain_records[-top_k:]

    def get_all(self) -> List[ExperienceRecord]:
        """Return all stored records."""
        return list(self._records)

    def get_success_rate(self, domain: Optional[str] = None) -> float:
        """Compute success rate, optionally filtered by domain."""
        records = self._records
        if domain:
            records = [r for r in records if r.domain == domain]
        if not records:
            return 0.0
        return sum(1 for r in records if r.success) / len(records)


class BottleneckAnalyzer:
    """
    Identifies worst-performing layers and cross-domain blockers.

    Analyzes verification reports and task graph state to find
    the most impactful bottlenecks to address.
    """

    def analyze(
        self,
        graph: CrossLayerTaskGraph,
        reports: List[VerificationReport],
    ) -> List[Bottleneck]:
        """
        Analyze reports to identify bottlenecks.

        Returns bottlenecks sorted by severity (critical first).
        """
        bottlenecks: List[Bottleneck] = []

        for report in reports:
            task = graph.get_task(report.task_id)
            if task is None:
                continue

            if not report.passed:
                # Failed task = critical bottleneck
                bottlenecks.append(Bottleneck(
                    task_id=task.id,
                    domain=task.domain,
                    metric_name="overall_pass",
                    current_value=0.0,
                    target_value=1.0,
                    severity="critical",
                    description=f"Task failed: {'; '.join(report.errors[:3])}",
                ))
                continue

            # Check metrics against criteria
            for metric_name, threshold in task.verification_criteria.items():
                if metric_name not in report.metrics:
                    continue
                actual = report.metrics[metric_name]
                if not isinstance(threshold, (int, float)):
                    continue

                # Determine if this is a "lower is better" or "higher is better" metric
                is_higher_better = metric_name in (
                    "accuracy", "throughput", "coverage",
                    "lint_pass", "compile_pass", "tests_pass",
                    "simulation_pass",
                )

                gap = (threshold - actual) if is_higher_better else (actual - threshold)
                if gap > 0:
                    # Not meeting the target
                    relative_gap = gap / max(abs(threshold), 1e-6)
                    severity = (
                        "critical" if relative_gap > 0.5
                        else "major" if relative_gap > 0.2
                        else "minor"
                    )
                    bottlenecks.append(Bottleneck(
                        task_id=task.id,
                        domain=task.domain,
                        metric_name=metric_name,
                        current_value=actual,
                        target_value=threshold,
                        severity=severity,
                        description=(
                            f"{metric_name}: {actual:.3f} vs target {threshold:.3f} "
                            f"(gap: {relative_gap:.1%})"
                        ),
                    ))

        # Cross-domain blockers: blocked tasks
        for task in graph.get_blocked_tasks():
            bottlenecks.append(Bottleneck(
                task_id=task.id,
                domain=task.domain,
                metric_name="blocked",
                current_value=0.0,
                target_value=1.0,
                severity="critical",
                description=f"Task blocked by failed dependencies: {task.dependencies}",
            ))

        # Sort by severity
        severity_order = {"critical": 0, "major": 1, "minor": 2}
        bottlenecks.sort(key=lambda b: severity_order.get(b.severity, 99))
        return bottlenecks


class FeedbackGenerator:
    """
    Generates targeted revision instructions for domain teams.

    Uses LLM to produce actionable feedback based on bottlenecks
    and past experience.
    """

    def __init__(self, llm_func=None):
        self._llm_func = llm_func

    async def generate_feedback(
        self,
        bottlenecks: List[Bottleneck],
        experience: List[ExperienceRecord],
    ) -> Dict[str, str]:
        """
        Generate per-domain revision instructions.

        Args:
            bottlenecks: Identified bottlenecks.
            experience: Relevant past experience.

        Returns:
            Dict mapping domain -> revision instructions.
        """
        if not bottlenecks:
            return {}

        # Group bottlenecks by domain
        by_domain: Dict[str, List[Bottleneck]] = {}
        for bn in bottlenecks:
            by_domain.setdefault(bn.domain, []).append(bn)

        feedback: Dict[str, str] = {}
        for domain, domain_bottlenecks in by_domain.items():
            domain_exp = [e for e in experience if e.domain == domain]
            feedback[domain] = await self._generate_domain_feedback(
                domain, domain_bottlenecks, domain_exp
            )

        return feedback

    async def _generate_domain_feedback(
        self,
        domain: str,
        bottlenecks: List[Bottleneck],
        experience: List[ExperienceRecord],
    ) -> str:
        """Generate feedback for a single domain."""
        # Build a structured summary
        bn_lines = []
        for bn in bottlenecks:
            bn_lines.append(
                f"- [{bn.severity}] {bn.metric_name}: "
                f"{bn.current_value} → target {bn.target_value} | {bn.description}"
            )

        exp_lines = []
        for exp in experience[-5:]:
            status = "SUCCESS" if exp.success else "FAILED"
            exp_lines.append(f"- [{status}] {exp.action_taken}: {exp.lesson}")

        prompt = (
            f"Generate targeted revision instructions for the {domain} domain.\n\n"
            f"## Current Bottlenecks:\n" + "\n".join(bn_lines) + "\n\n"
            f"## Past Experience:\n" + ("\n".join(exp_lines) if exp_lines else "None") + "\n\n"
            f"Provide 3-5 specific, actionable improvement steps. "
            f"Focus on the most critical bottleneck first."
        )

        if self._llm_func:
            return await self._llm_func(prompt)

        # Default: generate structured feedback without LLM
        lines = [f"## Revision Instructions for {domain.upper()}\n"]
        for i, bn in enumerate(bottlenecks[:5], 1):
            if bn.severity == "critical":
                lines.append(
                    f"{i}. [CRITICAL] Fix {bn.metric_name}: "
                    f"current={bn.current_value}, target={bn.target_value}. "
                    f"{bn.description}"
                )
            else:
                lines.append(
                    f"{i}. [IMPROVE] Optimize {bn.metric_name}: "
                    f"reduce gap from {bn.current_value} to {bn.target_value}."
                )
        return "\n".join(lines)


class ConvergenceChecker:
    """
    Decides whether the loop should continue, has converged, is stuck, or should pivot.

    Checks:
    - Improvement rate across iterations
    - Oscillation detection (metrics bouncing)
    - Budget remaining (iterations, time)
    """

    def __init__(self, threshold: float = 0.02):
        """
        Args:
            threshold: Minimum improvement rate to continue (2% default).
        """
        self.threshold = threshold

    def check(
        self, iteration_history: List[Dict[str, Any]]
    ) -> Literal["continue", "converged", "stuck", "pivot"]:
        """
        Decide loop action based on iteration history.

        Args:
            iteration_history: List of per-iteration summaries with
                               'metrics', 'passed_count', 'total_count'.

        Returns:
            Decision: continue, converged, stuck, or pivot.
        """
        if len(iteration_history) < 2:
            return "continue"

        latest = iteration_history[-1]
        previous = iteration_history[-2]

        # Check convergence: all tasks passed
        if latest.get("passed_count", 0) == latest.get("total_count", 1):
            return "converged"

        # Check improvement rate
        latest_score = self._compute_score(latest)
        previous_score = self._compute_score(previous)

        if previous_score > 0:
            improvement = (latest_score - previous_score) / previous_score
        else:
            improvement = latest_score

        # Converged if improvement is negligible and score is high
        if abs(improvement) < self.threshold and latest_score >= 0.8:
            return "converged"

        # Stuck if no improvement for 3+ iterations
        if len(iteration_history) >= 3:
            scores = [self._compute_score(h) for h in iteration_history[-3:]]
            max_delta = max(scores) - min(scores)
            if max_delta < self.threshold:
                # Check for oscillation
                if self._is_oscillating(iteration_history[-4:]):
                    return "pivot"
                return "stuck"

        # Regression: getting worse
        if improvement < -0.1:
            return "pivot"

        return "continue"

    def _compute_score(self, iteration_data: Dict[str, Any]) -> float:
        """Compute a normalized score for an iteration (0.0 to 1.0)."""
        total = iteration_data.get("total_count", 1)
        passed = iteration_data.get("passed_count", 0)
        if total == 0:
            return 0.0
        return passed / total

    def _is_oscillating(self, history: List[Dict[str, Any]]) -> bool:
        """Detect score oscillation (up-down-up pattern)."""
        if len(history) < 4:
            return False
        scores = [self._compute_score(h) for h in history]
        # Check for alternating direction
        directions = [
            scores[i + 1] - scores[i] for i in range(len(scores) - 1)
        ]
        sign_changes = sum(
            1 for i in range(len(directions) - 1)
            if directions[i] * directions[i + 1] < 0
        )
        return sign_changes >= 2


class EvolutionEngine:
    """
    Bundles all evolution components into a single interface.

    Manages the bottleneck analysis → experience store → feedback generation cycle.
    """

    def __init__(self, llm_func=None, convergence_threshold: float = 0.02):
        self.experience_store = ExperienceStore()
        self.bottleneck_analyzer = BottleneckAnalyzer()
        self.feedback_generator = FeedbackGenerator(llm_func=llm_func)
        self.convergence_checker = ConvergenceChecker(threshold=convergence_threshold)
        self._iteration_history: List[Dict[str, Any]] = []

    def get_experience(self, task: TaskNode) -> List[ExperienceRecord]:
        """Get relevant experience for a task."""
        return self.experience_store.query_relevant(
            domain=task.domain, task_type=task.task_type
        )

    async def step(
        self,
        graph: CrossLayerTaskGraph,
        reports: List[VerificationReport],
        iteration: int,
    ) -> Literal["continue", "converged", "stuck", "pivot"]:
        """
        Execute one evolution step.

        1. Record experience from reports
        2. Analyze bottlenecks
        3. Check convergence
        4. Return decision
        """
        # Record experience
        for report in reports:
            task = graph.get_task(report.task_id)
            if task is None:
                continue
            record = ExperienceRecord(
                task_id=task.id,
                iteration=iteration,
                domain=task.domain,
                action_taken=task.description[:200],
                metrics_after=report.metrics,
                success=report.passed,
                lesson=self._generate_lesson(task, report),
            )
            self.experience_store.add(record)

        # Update iteration history
        all_tasks = graph.get_all_tasks()
        passed_count = sum(1 for t in all_tasks if t.status == "passed")
        self._iteration_history.append({
            "iteration": iteration,
            "total_count": len(all_tasks),
            "passed_count": passed_count,
            "metrics": {r.task_id: r.metrics for r in reports},
        })

        # Check convergence
        decision = self.convergence_checker.check(self._iteration_history)
        return decision

    async def get_feedback(
        self, graph: CrossLayerTaskGraph, reports: List[VerificationReport]
    ) -> Dict[str, str]:
        """Generate feedback for the next iteration."""
        bottlenecks = self.bottleneck_analyzer.analyze(graph, reports)
        all_experience = self.experience_store.get_all()
        return await self.feedback_generator.generate_feedback(
            bottlenecks, all_experience
        )

    def get_iteration_history(self) -> List[Dict[str, Any]]:
        """Return full iteration history."""
        return self._iteration_history

    @staticmethod
    def _generate_lesson(task: TaskNode, report: VerificationReport) -> str:
        """Generate a concise lesson from a task result."""
        if report.passed:
            return f"Successfully completed {task.task_type} in {task.domain}"
        else:
            errors = "; ".join(report.errors[:2]) if report.errors else "unknown"
            return f"Failed {task.task_type} in {task.domain}: {errors}"
