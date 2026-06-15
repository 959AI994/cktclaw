"""
Tests for the CktClaw v3 System Loop — cross-domain closed-loop.

Test cases:
1. TaskGraph: build, query ready, complete, critical path
2. GoalDecomposer: mock LLM → verify graph structure
3. DomainTeams: mock tool execution → verify artifact collection
4. VerificationRunner: mock tool outputs → verify metrics extraction
5. EvolutionEngine: mock reports → verify bottleneck detection + feedback
6. ConvergenceChecker: improvement series → verify correct decisions
7. Full loop E2E: mock all LLM calls → verify iterations with convergence
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Ensure project root on path
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.loop.task_graph import TaskNode, CrossLayerTaskGraph
from cktclaw.loop.goal_decomposer import GoalDecomposer
from cktclaw.loop.domain_teams import (
    DomainTeam, EDATeam, ChipTeam, AIInfraTeam, TaskResult,
)
from cktclaw.loop.verification import VerificationRunner, VerificationReport
from cktclaw.loop.evolution import (
    ExperienceRecord,
    ExperienceStore,
    BottleneckAnalyzer,
    FeedbackGenerator,
    ConvergenceChecker,
    EvolutionEngine,
    Bottleneck,
)
from cktclaw.loop.controller import SystemLoopController, LoopConfig, LoopResult


def _run(coro):
    """Helper to run async tests without pytest-asyncio."""
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
# 1. TaskGraph Tests
# ═══════════════════════════════════════════════════════════════

class TestTaskNode:
    def test_create_default(self):
        node = TaskNode()
        assert node.domain == "eda"
        assert node.task_type == "generate"
        assert node.status == "pending"
        assert node.id.startswith("task_")

    def test_create_with_fields(self):
        node = TaskNode(
            id="eda_synth_1",
            domain="eda",
            task_type="generate",
            description="Synthesize top module",
            dependencies=["chip_rtl_1"],
            verification_criteria={"area_cells": 500},
        )
        assert node.id == "eda_synth_1"
        assert node.dependencies == ["chip_rtl_1"]
        assert node.verification_criteria == {"area_cells": 500}

    def test_to_dict_from_dict(self):
        node = TaskNode(
            id="test_1",
            domain="chip",
            task_type="verify",
            description="Run lint",
            dependencies=["dep_1"],
            verification_criteria={"lint_pass": 1.0},
            metrics={"lint_pass": 1.0},
            artifacts=["/tmp/out.v"],
            iteration=2,
        )
        d = node.to_dict()
        restored = TaskNode.from_dict(d)
        assert restored.id == "test_1"
        assert restored.domain == "chip"
        assert restored.metrics == {"lint_pass": 1.0}
        assert restored.iteration == 2


class TestCrossLayerTaskGraph:
    def _build_graph(self):
        """Build a sample 5-node graph across 3 domains."""
        graph = CrossLayerTaskGraph()
        graph.add_task(TaskNode(id="chip_rtl_1", domain="chip", description="Write RTL"))
        graph.add_task(TaskNode(id="chip_verif_1", domain="chip", description="Verify RTL",
                                dependencies=["chip_rtl_1"]))
        graph.add_task(TaskNode(id="eda_synth_1", domain="eda", description="Synthesize",
                                dependencies=["chip_rtl_1"]))
        graph.add_task(TaskNode(id="eda_pnr_1", domain="eda", description="Place & Route",
                                dependencies=["eda_synth_1"]))
        graph.add_task(TaskNode(id="ai_train_1", domain="ai_infra", description="Train model",
                                dependencies=["chip_verif_1"]))
        return graph

    def test_add_and_get_task(self):
        graph = CrossLayerTaskGraph()
        node = TaskNode(id="t1", domain="eda")
        graph.add_task(node)
        assert graph.get_task("t1") is node
        assert graph.get_task("nonexistent") is None

    def test_get_ready_tasks(self):
        graph = self._build_graph()
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "chip_rtl_1"

    def test_complete_task_unlocks_dependents(self):
        graph = self._build_graph()
        graph.complete_task("chip_rtl_1", status="passed", metrics={"area": 100})

        ready = graph.get_ready_tasks()
        ready_ids = {t.id for t in ready}
        assert "chip_verif_1" in ready_ids
        assert "eda_synth_1" in ready_ids
        assert "eda_pnr_1" not in ready_ids  # depends on eda_synth_1

    def test_complete_task_failed_blocks_dependents(self):
        graph = self._build_graph()
        graph.complete_task("chip_rtl_1", status="failed")

        blocked = graph.get_blocked_tasks()
        blocked_ids = {t.id for t in blocked}
        assert "chip_verif_1" in blocked_ids
        assert "eda_synth_1" in blocked_ids

    def test_get_critical_path(self):
        graph = self._build_graph()
        path = graph.get_critical_path()
        # Longest chain: chip_rtl_1 → eda_synth_1 → eda_pnr_1 (length 3)
        # or chip_rtl_1 → chip_verif_1 → ai_train_1 (length 3)
        assert len(path) == 3
        assert path[0].id == "chip_rtl_1"

    def test_get_domain_subgraph(self):
        graph = self._build_graph()
        eda_tasks = graph.get_domain_subgraph("eda")
        assert len(eda_tasks) == 2
        assert all(t.domain == "eda" for t in eda_tasks)

    def test_reset_failed_tasks(self):
        graph = self._build_graph()
        graph.complete_task("chip_rtl_1", status="failed")
        assert len(graph.get_blocked_tasks()) > 0

        graph.reset_failed_tasks(iteration=1)
        # After reset, failed/blocked become pending
        assert graph.get_task("chip_rtl_1").status == "pending"
        assert graph.get_task("chip_rtl_1").iteration == 1

    def test_serialization(self):
        graph = self._build_graph()
        d = graph.to_dict()
        restored = CrossLayerTaskGraph.from_dict(d)
        assert len(restored) == 5
        assert restored.get_task("chip_rtl_1").description == "Write RTL"

    def test_len_and_repr(self):
        graph = self._build_graph()
        assert len(graph) == 5
        r = repr(graph)
        assert "CrossLayerTaskGraph" in r


# ═══════════════════════════════════════════════════════════════
# 2. GoalDecomposer Tests
# ═══════════════════════════════════════════════════════════════

class TestGoalDecomposer:
    @pytest.fixture
    def mock_llm_output(self):
        return json.dumps({
            "tasks": [
                {
                    "id": "chip_rtl_1",
                    "domain": "chip",
                    "task_type": "generate",
                    "description": "Design a 4-bit adder RTL",
                    "dependencies": [],
                    "verification_criteria": {"lint_pass": 1.0},
                },
                {
                    "id": "eda_synth_1",
                    "domain": "eda",
                    "task_type": "generate",
                    "description": "Synthesize the adder",
                    "dependencies": ["chip_rtl_1"],
                    "verification_criteria": {"area_cells": 50},
                },
                {
                    "id": "ai_train_1",
                    "domain": "ai_infra",
                    "task_type": "generate",
                    "description": "Create training pipeline",
                    "dependencies": [],
                    "verification_criteria": {"compile_pass": 1.0},
                },
            ]
        })

    def test_decompose_with_mock_llm(self, mock_llm_output):
        async def mock_llm(prompt):
            return mock_llm_output

        decomposer = GoalDecomposer(llm_func=mock_llm)
        graph = _run(decomposer.decompose("design a 4-bit adder with training"))

        assert len(graph) == 3
        assert graph.get_task("chip_rtl_1") is not None
        assert graph.get_task("eda_synth_1").dependencies == ["chip_rtl_1"]
        assert graph.get_task("ai_train_1").domain == "ai_infra"

    def test_decompose_handles_json_in_code_block(self):
        output = '```json\n{"tasks": [{"id": "t1", "domain": "eda", "task_type": "generate", "description": "test", "dependencies": [], "verification_criteria": {}}]}\n```'

        async def mock_llm(prompt):
            return output

        decomposer = GoalDecomposer(llm_func=mock_llm)
        graph = _run(decomposer.decompose("test goal"))
        assert len(graph) == 1

    def test_decompose_empty_response(self):
        async def mock_llm(prompt):
            return ""

        decomposer = GoalDecomposer(llm_func=mock_llm)
        graph = _run(decomposer.decompose("test goal"))
        assert len(graph) == 0

    def test_normalize_domain(self):
        assert GoalDecomposer._normalize_domain("eda") == "eda"
        assert GoalDecomposer._normalize_domain("chip") == "chip"
        assert GoalDecomposer._normalize_domain("ai_infra") == "ai_infra"
        assert GoalDecomposer._normalize_domain("synthesis") == "eda"
        assert GoalDecomposer._normalize_domain("rtl_design") == "chip"
        assert GoalDecomposer._normalize_domain("training") == "ai_infra"

    def test_validate_graph_detects_missing_deps(self):
        decomposer = GoalDecomposer()
        graph = CrossLayerTaskGraph()
        graph.add_task(TaskNode(id="t1", dependencies=["nonexistent"]))
        warnings = decomposer._validate_graph(graph)
        assert any("non-existent" in w for w in warnings)


# ═══════════════════════════════════════════════════════════════
# 3. DomainTeams Tests
# ═══════════════════════════════════════════════════════════════

class TestDomainTeams:
    def test_eda_team_select_agents(self):
        team = EDATeam()
        task = TaskNode(id="t1", domain="eda", description="Synthesize the module")
        agents = team._select_agents(task)
        assert "chip-synthesis" in agents

    def test_chip_team_select_agents(self):
        team = ChipTeam()
        task = TaskNode(id="t1", domain="chip", description="Write RTL for adder")
        agents = team._select_agents(task)
        assert "chip-rtl" in agents

    def test_ai_infra_team_select_agents(self):
        team = AIInfraTeam()
        task = TaskNode(id="t1", domain="ai_infra",
                        description="Create training script for CNN")
        agents = team._select_agents(task)
        assert "ai-training" in agents

    def test_eda_team_select_agents_optimization(self):
        team = EDATeam()
        task = TaskNode(id="t1", domain="eda",
                        description="Optimize with RLTF")
        agents = team._select_agents(task)
        assert "rltf" in agents

    def test_build_context(self):
        team = EDATeam()
        task = TaskNode(
            id="t1", domain="eda", description="Synthesize",
            verification_criteria={"area": 100},
        )
        ctx = team._build_context(task, [])
        assert "Synthesize" in ctx
        assert "area" in ctx

    def test_execute_task_handles_error(self):
        """Test that execute_task gracefully handles agent runtime errors."""
        team = EDATeam()
        task = TaskNode(id="t1", domain="eda", description="Synthesize")

        with patch("cktclaw.agents.runtime.get_agent_runtime") as mock_rt:
            mock_rt.side_effect = RuntimeError("No runtime")
            result = _run(team.execute_task(task))
            assert not result.success
            assert "No runtime" in result.error


# ═══════════════════════════════════════════════════════════════
# 4. VerificationRunner Tests
# ═══════════════════════════════════════════════════════════════

class TestVerificationRunner:
    def test_extract_yosys_area(self):
        output = "   Number of cells:          42\n   Number of wires:          30\n"
        area = VerificationRunner._extract_yosys_area(output)
        assert area == 42.0

    def test_extract_abc_stats(self):
        output = "i/o =    8/   4  lat =    0  and =   23  lev =    5"
        metrics = VerificationRunner._extract_abc_stats(output)
        assert metrics["and_nodes"] == 23.0
        assert metrics["logic_levels"] == 5.0

    def test_extract_sta_delay(self):
        output = "Startpoint: a\nEndpoint: z\nslack = -0.35\n"
        delay = VerificationRunner._extract_sta_delay(output)
        assert delay == 0.35

    def test_check_criteria_passes(self):
        runner = VerificationRunner()
        criteria = {"area_cells": 100, "compile_pass": 1.0}
        metrics = {"area_cells": 80, "compile_pass": 1.0}
        warnings: list = []
        assert runner._check_criteria(criteria, metrics, warnings) is True

    def test_check_criteria_fails_area(self):
        runner = VerificationRunner()
        criteria = {"area_cells": 50}  # max threshold
        metrics = {"area_cells": 80}  # exceeds
        warnings: list = []
        assert runner._check_criteria(criteria, metrics, warnings) is False

    def test_check_criteria_fails_accuracy(self):
        runner = VerificationRunner()
        criteria = {"accuracy": 0.9}  # min threshold
        metrics = {"accuracy": 0.7}  # below
        warnings: list = []
        assert runner._check_criteria(criteria, metrics, warnings) is False

    def test_check_criteria_empty(self):
        runner = VerificationRunner()
        assert runner._check_criteria({}, {}, []) is True

    def test_verify_task_no_artifacts(self):
        runner = VerificationRunner()
        task = TaskNode(id="t1", domain="eda", description="test")
        report = _run(runner.verify_task(task, []))
        assert not report.passed
        assert report.errors

    def test_verify_ai_infra_no_python(self):
        runner = VerificationRunner()
        task = TaskNode(id="t1", domain="ai_infra", description="test")
        report = _run(runner.verify_task(task, ["/tmp/data.csv"]))
        assert not report.passed
        assert "No Python artifacts" in report.errors[0]


# ═══════════════════════════════════════════════════════════════
# 5. EvolutionEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestExperienceStore:
    def test_add_and_query(self):
        store = ExperienceStore()
        record = ExperienceRecord(
            task_id="t1", iteration=0, domain="eda",
            action_taken="synthesis", success=True, lesson="Worked well",
        )
        store.add(record)
        results = store.query_relevant("eda")
        assert len(results) == 1
        assert results[0].lesson == "Worked well"

    def test_success_rate(self):
        store = ExperienceStore()
        store.add(ExperienceRecord(task_id="t1", iteration=0, domain="eda",
                                   action_taken="a", success=True, lesson=""))
        store.add(ExperienceRecord(task_id="t2", iteration=0, domain="eda",
                                   action_taken="b", success=False, lesson=""))
        store.add(ExperienceRecord(task_id="t3", iteration=0, domain="chip",
                                   action_taken="c", success=True, lesson=""))
        assert store.get_success_rate() == pytest.approx(2 / 3)
        assert store.get_success_rate("eda") == 0.5
        assert store.get_success_rate("chip") == 1.0


class TestBottleneckAnalyzer:
    def test_identify_failed_task(self):
        analyzer = BottleneckAnalyzer()
        graph = CrossLayerTaskGraph()
        graph.add_task(TaskNode(id="t1", domain="eda",
                                verification_criteria={"area": 100}))

        report = VerificationReport(
            task_id="t1", passed=False, errors=["Synthesis failed"]
        )
        bottlenecks = analyzer.analyze(graph, [report])
        assert len(bottlenecks) >= 1
        assert bottlenecks[0].severity == "critical"
        assert bottlenecks[0].task_id == "t1"

    def test_identify_metric_gap(self):
        analyzer = BottleneckAnalyzer()
        graph = CrossLayerTaskGraph()
        graph.add_task(TaskNode(id="t1", domain="eda",
                                verification_criteria={"area_cells": 50}))

        report = VerificationReport(
            task_id="t1", passed=True, metrics={"area_cells": 80}
        )
        bottlenecks = analyzer.analyze(graph, [report])
        # area_cells 80 > threshold 50 = bottleneck
        assert len(bottlenecks) >= 1
        assert bottlenecks[0].metric_name == "area_cells"

    def test_no_bottlenecks_when_passing(self):
        analyzer = BottleneckAnalyzer()
        graph = CrossLayerTaskGraph()
        graph.add_task(TaskNode(id="t1", domain="eda",
                                verification_criteria={"area_cells": 100}))

        report = VerificationReport(
            task_id="t1", passed=True, metrics={"area_cells": 80}
        )
        bottlenecks = analyzer.analyze(graph, [report])
        assert len(bottlenecks) == 0


class TestFeedbackGenerator:
    def test_generate_feedback_no_llm(self):
        gen = FeedbackGenerator()
        bottlenecks = [
            Bottleneck(
                task_id="t1", domain="eda", metric_name="area_cells",
                current_value=80, target_value=50, severity="major",
                description="Area too large",
            )
        ]
        feedback = _run(gen.generate_feedback(bottlenecks, []))
        assert "eda" in feedback
        assert "area_cells" in feedback["eda"]

    def test_generate_feedback_with_llm(self):
        async def mock_llm(prompt):
            return "1. Reduce logic depth\n2. Use smaller cells"

        gen = FeedbackGenerator(llm_func=mock_llm)
        bottlenecks = [
            Bottleneck(task_id="t1", domain="eda", metric_name="area",
                       current_value=100, target_value=50, severity="critical",
                       description="too large")
        ]
        feedback = _run(gen.generate_feedback(bottlenecks, []))
        assert "eda" in feedback
        assert "Reduce" in feedback["eda"]


class TestConvergenceChecker:
    def test_continue_on_first_iteration(self):
        checker = ConvergenceChecker()
        result = checker.check([{"total_count": 5, "passed_count": 2}])
        assert result == "continue"

    def test_converged_all_passed(self):
        checker = ConvergenceChecker()
        history = [
            {"total_count": 5, "passed_count": 3},
            {"total_count": 5, "passed_count": 5},
        ]
        result = checker.check(history)
        assert result == "converged"

    def test_converged_near_target(self):
        checker = ConvergenceChecker(threshold=0.02)
        history = [
            {"total_count": 10, "passed_count": 8},
            {"total_count": 10, "passed_count": 8},  # no improvement, score = 0.8
        ]
        result = checker.check(history)
        assert result == "converged"

    def test_stuck_no_improvement(self):
        checker = ConvergenceChecker(threshold=0.02)
        history = [
            {"total_count": 10, "passed_count": 3},
            {"total_count": 10, "passed_count": 3},
            {"total_count": 10, "passed_count": 3},
        ]
        result = checker.check(history)
        assert result == "stuck"

    def test_continue_with_improvement(self):
        checker = ConvergenceChecker(threshold=0.02)
        history = [
            {"total_count": 10, "passed_count": 3},
            {"total_count": 10, "passed_count": 5},
        ]
        result = checker.check(history)
        assert result == "continue"

    def test_pivot_on_regression(self):
        checker = ConvergenceChecker(threshold=0.02)
        history = [
            {"total_count": 10, "passed_count": 6},
            {"total_count": 10, "passed_count": 4},
        ]
        result = checker.check(history)
        assert result == "pivot"


# ═══════════════════════════════════════════════════════════════
# 6. Full Loop E2E Tests
# ═══════════════════════════════════════════════════════════════

class TestSystemLoopController:
    @pytest.fixture
    def mock_graph_json(self):
        return json.dumps({
            "tasks": [
                {
                    "id": "chip_rtl_1",
                    "domain": "chip",
                    "task_type": "generate",
                    "description": "Write 4-bit adder RTL",
                    "dependencies": [],
                    "verification_criteria": {"lint_pass": 1.0},
                },
                {
                    "id": "eda_synth_1",
                    "domain": "eda",
                    "task_type": "generate",
                    "description": "Synthesize adder",
                    "dependencies": ["chip_rtl_1"],
                    "verification_criteria": {"area_cells": 100},
                },
            ]
        })

    def test_loop_converges_with_mocks(self, mock_graph_json):
        """E2E test: mock LLM + mock teams → verify convergence in 2 iterations."""
        call_count = [0]

        async def mock_llm(prompt):
            return mock_graph_json

        async def _test():
            config = LoopConfig(max_iterations=5, parallel_tasks=True)
            controller = SystemLoopController(config=config, llm_func=mock_llm)

            # Mock domain teams to always succeed
            async def mock_execute(task, experience=None):
                call_count[0] += 1
                return TaskResult(
                    task_id=task.id,
                    success=True,
                    artifacts=["/tmp/out.v"],
                    output="done",
                )

            for team in controller.teams.values():
                team.execute_task = mock_execute

            # Mock verifier to always pass
            async def mock_verify(task, artifacts):
                return VerificationReport(
                    task_id=task.id,
                    passed=True,
                    metrics={"area_cells": 50, "lint_pass": 1.0},
                )

            controller.verifier.verify_task = mock_verify

            result = await controller.run("design a 4-bit adder")
            return result

        result = _run(_test())
        assert result.status == "converged"
        assert result.passed_tasks == 2
        assert result.total_tasks == 2
        assert call_count[0] >= 2

    def test_loop_handles_failures_then_converges(self, mock_graph_json):
        """Test that the loop retries failed tasks and eventually converges."""
        iteration_counter = [0]

        async def mock_llm(prompt):
            return mock_graph_json

        async def _test():
            config = LoopConfig(max_iterations=5)
            controller = SystemLoopController(config=config, llm_func=mock_llm)

            # Mock teams: always succeed
            async def mock_execute(task, experience=None):
                return TaskResult(task_id=task.id, success=True, artifacts=["/tmp/x.v"])

            for team in controller.teams.values():
                team.execute_task = mock_execute

            # Mock verifier: fail first iteration, pass after
            async def mock_verify(task, artifacts):
                iteration_counter[0] += 1
                if iteration_counter[0] <= 2:  # First iteration (2 tasks) fails
                    return VerificationReport(
                        task_id=task.id, passed=False,
                        errors=["First attempt failed"],
                        metrics={"area_cells": 200},
                    )
                return VerificationReport(
                    task_id=task.id, passed=True,
                    metrics={"area_cells": 50, "lint_pass": 1.0},
                )

            controller.verifier.verify_task = mock_verify

            return await controller.run("design a 4-bit adder")

        result = _run(_test())
        assert result.iterations_completed >= 2
        assert result.passed_tasks == 2

    def test_loop_respects_max_iterations(self, mock_graph_json):
        """Test that the loop stops at max_iterations."""
        async def mock_llm(prompt):
            return mock_graph_json

        async def _test():
            config = LoopConfig(max_iterations=2)
            controller = SystemLoopController(config=config, llm_func=mock_llm)

            async def mock_execute(task, experience=None):
                return TaskResult(task_id=task.id, success=True, artifacts=["/tmp/x.v"])

            for team in controller.teams.values():
                team.execute_task = mock_execute

            # Always fail verification
            async def mock_verify(task, artifacts):
                return VerificationReport(
                    task_id=task.id, passed=False,
                    errors=["Always fails"],
                )

            controller.verifier.verify_task = mock_verify

            return await controller.run("design something")

        result = _run(_test())
        assert result.iterations_completed <= 2

    def test_loop_empty_graph(self):
        """Test handling of empty goal decomposition."""
        async def mock_llm(prompt):
            return "{}"  # No tasks

        async def _test():
            config = LoopConfig(max_iterations=3)
            controller = SystemLoopController(config=config, llm_func=mock_llm)
            return await controller.run("empty goal")

        result = _run(_test())
        assert result.status == "error"
        assert result.total_tasks == 0

    def test_loop_result_serialization(self, mock_graph_json):
        """Test that LoopResult serializes correctly."""
        async def mock_llm(prompt):
            return mock_graph_json

        async def _test():
            config = LoopConfig(max_iterations=1)
            controller = SystemLoopController(config=config, llm_func=mock_llm)

            async def mock_execute(task, experience=None):
                return TaskResult(task_id=task.id, success=True, artifacts=[])

            for team in controller.teams.values():
                team.execute_task = mock_execute

            async def mock_verify(task, artifacts):
                return VerificationReport(task_id=task.id, passed=True, metrics={})

            controller.verifier.verify_task = mock_verify

            return await controller.run("test")

        result = _run(_test())
        d = result.to_dict()
        assert "session_id" in d
        assert "status" in d
        assert "goal" in d


# ═══════════════════════════════════════════════════════════════
# 7. Module Import Tests
# ═══════════════════════════════════════════════════════════════

class TestModuleImports:
    def test_import_loop_module(self):
        from cktclaw.loop import (
            TaskNode,
            CrossLayerTaskGraph,
            GoalDecomposer,
            DomainTeam,
            EDATeam,
            ChipTeam,
            AIInfraTeam,
            VerificationRunner,
            VerificationReport,
            ExperienceRecord,
            ExperienceStore,
            BottleneckAnalyzer,
            FeedbackGenerator,
            ConvergenceChecker,
            SystemLoopController,
            LoopConfig,
            LoopResult,
        )
        assert TaskNode is not None
        assert SystemLoopController is not None

    def test_version_updated(self):
        import cktclaw
        assert cktclaw.__version__ == "3.0.0"
