"""
Agent Tools - Agent Tools

Implements agent tools.

Core features:
1. AgentTool - Create sub-agents
2. SendMessageTool - Continue agent
3. TaskStopTool - Stop agent
"""

import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class AgentConfig:
    """Agent configuration"""
    agent_id: str
    name: str
    description: str
    system_prompt: str
    max_turns: int = 10
    model: str = "deepseek-chat"


@dataclass
class AgentResult:
    """Agent execution result"""
    agent_id: str
    status: str  # running, completed, failed, killed
    output: str
    metadata: Optional[Dict[str, Any]] = None


class AgentTool:
    """
    Agent tool

    Create and manage sub-agents
    """

    def __init__(self):
        """Initialize agent tool"""
        self.active_agents: Dict[str, AgentConfig] = {}
        self.agent_results: Dict[str, AgentResult] = {}

    async def create_agent(
        self,
        name: str,
        description: str,
        system_prompt: str,
        initial_message: str,
        max_turns: int = 10,
        model: str = "deepseek-chat"
    ) -> AgentResult:
        """
        Create sub-agent

        Args:
            name: Agent name
            description: Agent description
            system_prompt: System prompt
            initial_message: Initial message
            max_turns: Maximum turns
            model: Model name

        Returns:
            Agent execution result
        """
        # Generate agent ID
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"

        # Create agent configuration
        config = AgentConfig(
            agent_id=agent_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            max_turns=max_turns,
            model=model
        )

        # Save configuration
        self.active_agents[agent_id] = config

        # Create result
        result = AgentResult(
            agent_id=agent_id,
            status="running",
            output=f"Agent '{name}' created with ID: {agent_id}\n"
                   f"Initial message: {initial_message}",
            metadata={
                "name": name,
                "description": description,
                "created_at": datetime.now().isoformat(),
            }
        )

        self.agent_results[agent_id] = result

        return result

    async def send_message(
        self,
        agent_id: str,
        message: str
    ) -> AgentResult:
        """
        Send message to agent

        Args:
            agent_id: Agent ID
            message: Message content

        Returns:
            Agent execution result
        """
        if agent_id not in self.active_agents:
            raise ValueError(f"Agent not found: {agent_id}")

        config = self.active_agents[agent_id]
        result = self.agent_results[agent_id]

        # Update result
        result.output += f"\n\nUser: {message}\nAgent: Processing..."

        return result

    async def stop_agent(
        self,
        agent_id: str,
        reason: str = "User requested"
    ) -> AgentResult:
        """
        Stop agent

        Args:
            agent_id: Agent ID
            reason: Stop reason

        Returns:
            Agent execution result
        """
        if agent_id not in self.active_agents:
            raise ValueError(f"Agent not found: {agent_id}")

        result = self.agent_results[agent_id]
        result.status = "killed"
        result.output += f"\n\nAgent stopped: {reason}"

        # Clean up
        self.active_agents.pop(agent_id, None)

        return result

    def get_agent_status(self, agent_id: str) -> Optional[AgentResult]:
        """
        Get agent status

        Args:
            agent_id: Agent ID

        Returns:
            Agent execution result
        """
        return self.agent_results.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all agents

        Returns:
            Agent list
        """
        agents = []
        for agent_id, config in self.active_agents.items():
            result = self.agent_results.get(agent_id)
            agents.append({
                "agent_id": agent_id,
                "name": config.name,
                "description": config.description,
                "status": result.status if result else "unknown",
            })
        return agents


class SendMessageTool:
    """
    Send message tool

    Send message to agent to continue conversation
    """

    def __init__(self, agent_tool: AgentTool):
        """
        Initialize send message tool

        Args:
            agent_tool: Agent tool instance
        """
        self.agent_tool = agent_tool

    async def send(
        self,
        agent_id: str,
        message: str
    ) -> AgentResult:
        """
        Send message

        Args:
            agent_id: Agent ID
            message: Message content

        Returns:
            Agent execution result
        """
        return await self.agent_tool.send_message(agent_id, message)


class TaskStopTool:
    """
    Task stop tool

    Stop running agent
    """

    def __init__(self, agent_tool: AgentTool):
        """
        Initialize task stop tool

        Args:
            agent_tool: Agent tool instance
        """
        self.agent_tool = agent_tool

    async def stop(
        self,
        agent_id: str,
        reason: str = "User requested"
    ) -> AgentResult:
        """
        Stop task

        Args:
            agent_id: Agent ID
            reason: Stop reason

        Returns:
            Agent execution result
        """
        return await self.agent_tool.stop_agent(agent_id, reason)


# Global agent tool instance
_global_agent_tool: Optional[AgentTool] = None


def get_agent_tool() -> AgentTool:
    """
    Get global agent tool instance

    Returns:
        Agent tool instance
    """
    global _global_agent_tool

    if _global_agent_tool is None:
        _global_agent_tool = AgentTool()

    return _global_agent_tool


# Tool registration
AGENT_TOOLS = {
    "Agent": AgentTool,
    "SendMessage": SendMessageTool,
    "TaskStop": TaskStopTool,
}
