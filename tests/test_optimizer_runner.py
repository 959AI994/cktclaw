"""Unit tests for OptimizerAgent EvolutionEngine integration."""

from cktclaw.agents.runners.optimizer_runner import _bottlenecks_from_design_state, _format_evolution_report


def test_bottlenecks_from_qor():
    data = {
        "orchestrator_qor": {
            "synthesis": {"area": 2.5, "delay": 1.8},
        },
        "multi_agent": {
            "agent_status": {"eda_agent": "failed"},
        },
    }
    bottlenecks = _bottlenecks_from_design_state(data)
    assert len(bottlenecks) >= 2
    domains = {b.domain for b in bottlenecks}
    assert "synthesis" in domains
    assert "eda" in domains


def test_format_evolution_report_empty():
    report = _format_evolution_report({}, [])
    assert "Optimization Report" in report
    assert "No critical bottlenecks" in report
