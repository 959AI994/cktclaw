"""
WorkerAgent — executes tasks using LLM + tools in a query loop.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentBudget, AgentStatus
from .protocol import EventType

logger = logging.getLogger(__name__)


class WorkerAgent(BaseAgent):
    """
    A worker agent that executes tasks autonomously.

    Runs a query loop: LLM generates a response, if it contains tool calls
    they are executed and results fed back, until the LLM produces a final
    text response or budget is exceeded.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str = "",
        budget: Optional[AgentBudget] = None,
        allowed_tools: Optional[List[str]] = None,
        model: str = "deepseek",
        **kwargs,
    ):
        super().__init__(name=name, system_prompt=system_prompt, budget=budget, **kwargs)
        self.model = model
        if allowed_tools is not None:
            self.budget.allowed_tools = allowed_tools

    async def run(self, initial_message: str) -> str:
        """
        Execute the worker's task via LLM + tool query loop.

        Args:
            initial_message: Task description.

        Returns:
            Final text output from the agent.
        """
        from ..llm import get_model_router
        from ..tools import get_tool_registry

        self.status = AgentStatus.RUNNING
        self.budget.started_at = datetime.now().isoformat()
        self._emit(EventType.STARTED, {"task": initial_message})

        router = get_model_router()
        registry = get_tool_registry()

        # Get provider
        provider = router.get_provider(self.model) or router.current_provider
        if not provider:
            self.status = AgentStatus.FAILED
            self.error = "No LLM provider available"
            self._emit(EventType.FAILED, {"error": self.error})
            return ""

        # Get available tools
        available_tools = registry.list_tools()
        if self.budget.allowed_tools is not None:
            available_tools = [
                t for t in available_tools
                if t.name in self.budget.allowed_tools
            ]

        # Build tool schemas for the provider
        tool_schemas = [t.to_openai_schema() for t in available_tools]

        # Initialize messages
        from ..llm.base import ChatMessage
        from ..llm.types import MessageRole

        messages = []
        if self.system_prompt:
            messages.append(ChatMessage(
                role=MessageRole.SYSTEM,
                content=self.system_prompt,
            ))
        messages.append(ChatMessage(
            role=MessageRole.USER,
            content=initial_message,
        ))

        # Query loop
        while True:
            # Check budget
            exceeded = self.budget.is_exceeded()
            if exceeded:
                self.status = AgentStatus.BUDGET_EXCEEDED
                self.error = f"Budget exceeded: {exceeded}"
                self._emit(EventType.BUDGET_EXCEEDED, {"reason": exceeded})
                break

            # Check if killed
            if self.status == AgentStatus.KILLED:
                break

            # Call LLM
            try:
                response = await provider.chat(
                    messages=messages,
                    tools=tool_schemas if available_tools else None,
                    temperature=0.3,
                    max_tokens=4096,
                )
            except Exception as e:
                self.status = AgentStatus.FAILED
                self.error = f"LLM call failed: {str(e)}"
                self._emit(EventType.FAILED, {"error": self.error})
                break

            # Record usage
            self.budget.record_turn(
                tokens=response.total_tokens,
                tool_calls=len(response.tool_calls),
            )

            if response.has_tool_calls:
                # Execute tool calls
                messages.append(ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                ))

                for tc in response.tool_calls:
                    self._emit(EventType.TOOL_CALL, {
                        "tool": tc.name,
                        "args": tc.arguments,
                    })

                    # Find and execute tool
                    tool = registry.get(tc.name)
                    if tool:
                        from ..tools.base import ToolContext
                        ctx = ToolContext(session_id=self.agent_id)

                        try:
                            result = await tool.execute(tc.arguments, ctx)
                            result_content = result.output if result.success else f"Error: {result.error}"
                        except Exception as e:
                            result_content = f"Tool execution error: {str(e)}"
                    else:
                        result_content = f"Tool not found: {tc.name}"

                    self._emit(EventType.TOOL_RESULT, {
                        "tool": tc.name,
                        "success": tool is not None,
                    })

                    messages.append(ChatMessage(
                        role=MessageRole.TOOL,
                        content=result_content,
                        tool_call_id=tc.id,
                    ))
            else:
                # No tool calls — this is the final response
                self.result = response.content
                self.status = AgentStatus.COMPLETED
                self._emit(EventType.COMPLETED, {
                    "summary": response.content[:200],
                    "result": response.content,
                })
                break

        self._messages = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]
        return self.result
