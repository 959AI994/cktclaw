"""
Cross-Layer Task Graph — backbone DAG for the system closed loop.

Represents decomposed system goals as a directed acyclic graph of
cross-domain tasks with dependencies, verification criteria, and domain tags.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class TaskNode:
    """A single task in the cross-layer task graph."""

    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    domain: Literal["eda", "chip", "ai_infra"] = "eda"
    task_type: Literal["generate", "verify", "analyze"] = "generate"
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    verification_criteria: Dict[str, Any] = field(default_factory=dict)
    status: Literal["pending", "running", "passed", "failed", "blocked"] = "pending"
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    iteration: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "task_type": self.task_type,
            "description": self.description,
            "dependencies": self.dependencies,
            "verification_criteria": self.verification_criteria,
            "status": self.status,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNode":
        return cls(
            id=data.get("id", f"task_{uuid.uuid4().hex[:8]}"),
            domain=data.get("domain", "eda"),
            task_type=data.get("task_type", "generate"),
            description=data.get("description", ""),
            dependencies=data.get("dependencies", []),
            verification_criteria=data.get("verification_criteria", {}),
            status=data.get("status", "pending"),
            artifacts=data.get("artifacts", []),
            metrics=data.get("metrics", {}),
            iteration=data.get("iteration", 0),
        )


class CrossLayerTaskGraph:
    """
    DAG of cross-domain tasks with dependency tracking.

    Provides:
    - Topological ordering awareness
    - Ready-task queries (all deps satisfied)
    - Critical path computation
    - Domain-level subgraph extraction
    - Full serialization for persistence
    """

    def __init__(self):
        self._nodes: Dict[str, TaskNode] = {}

    @property
    def nodes(self) -> Dict[str, TaskNode]:
        return self._nodes

    def add_task(self, node: TaskNode) -> None:
        """Add a task node to the graph."""
        self._nodes[node.id] = node

    def get_task(self, task_id: str) -> Optional[TaskNode]:
        """Retrieve a task by ID."""
        return self._nodes.get(task_id)

    def get_ready_tasks(self) -> List[TaskNode]:
        """Return tasks whose dependencies are all satisfied (passed)."""
        ready = []
        for node in self._nodes.values():
            if node.status != "pending":
                continue
            deps_met = all(
                self._nodes.get(dep_id) is not None
                and self._nodes[dep_id].status == "passed"
                for dep_id in node.dependencies
            )
            if deps_met:
                ready.append(node)
        return ready

    def complete_task(
        self,
        task_id: str,
        status: Literal["passed", "failed"],
        metrics: Optional[Dict[str, float]] = None,
        artifacts: Optional[List[str]] = None,
    ) -> None:
        """Mark a task as completed with its results."""
        node = self._nodes.get(task_id)
        if node is None:
            raise KeyError(f"Task {task_id} not found in graph")
        node.status = status
        if metrics:
            node.metrics.update(metrics)
        if artifacts:
            node.artifacts.extend(artifacts)
        # Update blocked tasks
        self._update_blocked_status()

    def _update_blocked_status(self) -> None:
        """Re-evaluate blocked status for pending tasks."""
        for node in self._nodes.values():
            if node.status != "pending":
                continue
            has_failed_dep = any(
                self._nodes.get(dep_id) is not None
                and self._nodes[dep_id].status == "failed"
                for dep_id in node.dependencies
            )
            if has_failed_dep:
                node.status = "blocked"

    def get_blocked_tasks(self) -> List[TaskNode]:
        """Return tasks that are blocked by failed dependencies."""
        return [n for n in self._nodes.values() if n.status == "blocked"]

    def get_critical_path(self) -> List[TaskNode]:
        """
        Compute the critical path (longest dependency chain) in the graph.

        Uses BFS from all sources, tracking the longest path to each node.
        Returns the chain of nodes forming the longest path.
        """
        if not self._nodes:
            return []

        # Find nodes with no dependencies (sources)
        sources = [
            n for n in self._nodes.values() if not n.dependencies
        ]
        if not sources:
            return list(self._nodes.values())[:1]

        # BFS to compute longest path to each node
        dist: Dict[str, int] = {nid: 0 for nid in self._nodes}
        pred: Dict[str, Optional[str]] = {nid: None for nid in self._nodes}

        # Topological sort via Kahn's algorithm
        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self._nodes}

        for node in self._nodes.values():
            for dep_id in node.dependencies:
                if dep_id in self._nodes:
                    adj[dep_id].append(node.id)
                    in_degree[node.id] += 1

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        topo_order: List[str] = []

        while queue:
            nid = queue.popleft()
            topo_order.append(nid)
            for succ in adj[nid]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # Compute longest path using topo order
        for nid in topo_order:
            for succ in adj[nid]:
                if dist[nid] + 1 > dist[succ]:
                    dist[succ] = dist[nid] + 1
                    pred[succ] = nid

        # Find the end of the longest path
        end_id = max(dist, key=lambda k: dist[k])

        # Reconstruct path
        path: List[str] = []
        current: Optional[str] = end_id
        while current is not None:
            path.append(current)
            current = pred[current]
        path.reverse()

        return [self._nodes[nid] for nid in path if nid in self._nodes]

    def get_domain_subgraph(self, domain: str) -> List[TaskNode]:
        """Return all tasks belonging to a specific domain."""
        return [n for n in self._nodes.values() if n.domain == domain]

    def get_all_tasks(self) -> List[TaskNode]:
        """Return all tasks in the graph."""
        return list(self._nodes.values())

    def reset_failed_tasks(self, iteration: int) -> None:
        """Reset failed/blocked tasks for a new iteration attempt."""
        for node in self._nodes.values():
            if node.status in ("failed", "blocked"):
                node.status = "pending"
                node.iteration = iteration
                node.metrics.clear()
                node.artifacts.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire graph for persistence."""
        return {
            "nodes": [node.to_dict() for node in self._nodes.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossLayerTaskGraph":
        """Deserialize a graph from a dict."""
        graph = cls()
        for node_data in data.get("nodes", []):
            graph.add_task(TaskNode.from_dict(node_data))
        return graph

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        domains = {}
        for n in self._nodes.values():
            domains.setdefault(n.domain, []).append(n.status)
        parts = [f"{d}: {len(s)} tasks" for d, s in domains.items()]
        return f"CrossLayerTaskGraph({', '.join(parts)})"
