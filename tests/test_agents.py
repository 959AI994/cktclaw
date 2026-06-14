"""
Tests for Agent Runtime.
"""

import asyncio

import pytest

from cktclaw.agents.base import BaseAgent, AgentBudget, AgentStatus
from cktclaw.agents.protocol import AgentMessage, AgentEvent, EventType
from cktclaw.agents.runtime import AgentRuntime


class TestAgentBudget:
    def test_default_budget(self):
        b = AgentBudget()
        assert b.max_turns == 20
        assert b.max_tokens == 100_000
        assert b.is_exceeded() is None

    def test_turns_exceeded(self):
        b = AgentBudget(max_turns=2)
        b.record_turn()
        assert b.is_exceeded() is None
        b.record_turn()
        assert b.is_exceeded() is not None
        assert "max_turns" in b.is_exceeded()

    def test_tokens_exceeded(self):
        b = AgentBudget(max_tokens=100)
        b.record_turn(tokens=50)
        assert b.is_exceeded() is None
        b.record_turn(tokens=60)
        assert "max_tokens" in b.is_exceeded()


class TestAgentEvent:
    def test_completed_notification(self):
        event = AgentEvent(
            agent_id="test-001",
            event_type=EventType.COMPLETED,
            data={"summary": "done", "result": "all good"},
        )
        notification = event.to_notification()
        assert "<task-notification>" in notification
        assert "test-001" in notification
        assert "completed" in notification

    def test_failed_notification(self):
        event = AgentEvent(
            agent_id="test-002",
            event_type=EventType.FAILED,
            data={"error": "something broke"},
        )
        notification = event.to_notification()
        assert "failed" in notification


class TestAgentRuntime:
    def test_create_runtime(self):
        runtime = AgentRuntime(max_concurrent=3)
        assert runtime.max_concurrent == 3
        assert runtime.list_agents() == []

    def test_event_listener(self):
        runtime = AgentRuntime()
        events = []
        runtime.on_event(lambda e: events.append(e))

        # Spawn would emit an event, but we can't easily test without
        # a real LLM provider. Test the listener mechanism itself.
        event = AgentEvent(
            agent_id="test",
            event_type=EventType.SPAWNED,
            data={"name": "test"},
        )
        runtime._broadcast_event(event)
        assert len(events) == 1
        assert events[0].event_type == EventType.SPAWNED
