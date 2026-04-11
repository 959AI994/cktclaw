"""
Agent Tools - 智能体工具

参考 Claude Code 的智能体工具实现。

核心功能：
1. AgentTool - 生成子智能体
2. SendMessageTool - 继续智能体
3. TaskStopTool - 停止智能体
"""

import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class AgentConfig:
    """智能体配置"""
    agent_id: str
    name: str
    description: str
    system_prompt: str
    max_turns: int = 10
    model: str = "deepseek-chat"


@dataclass
class AgentResult:
    """智能体执行结果"""
    agent_id: str
    status: str  # running, completed, failed, killed
    output: str
    metadata: Optional[Dict[str, Any]] = None


class AgentTool:
    """
    智能体工具

    生成和管理子智能体
    """

    def __init__(self):
        """初始化智能体工具"""
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
        创建子智能体

        Args:
            name: 智能体名称
            description: 智能体描述
            system_prompt: 系统提示词
            initial_message: 初始消息
            max_turns: 最大轮次
            model: 模型名称

        Returns:
            智能体执行结果
        """
        # 生成智能体 ID
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"

        # 创建智能体配置
        config = AgentConfig(
            agent_id=agent_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            max_turns=max_turns,
            model=model
        )

        # 保存配置
        self.active_agents[agent_id] = config

        # 创建结果
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
        向智能体发送消息

        Args:
            agent_id: 智能体 ID
            message: 消息内容

        Returns:
            智能体执行结果
        """
        if agent_id not in self.active_agents:
            raise ValueError(f"Agent not found: {agent_id}")

        config = self.active_agents[agent_id]
        result = self.agent_results[agent_id]

        # 更新结果
        result.output += f"\n\nUser: {message}\nAgent: Processing..."

        return result

    async def stop_agent(
        self,
        agent_id: str,
        reason: str = "User requested"
    ) -> AgentResult:
        """
        停止智能体

        Args:
            agent_id: 智能体 ID
            reason: 停止原因

        Returns:
            智能体执行结果
        """
        if agent_id not in self.active_agents:
            raise ValueError(f"Agent not found: {agent_id}")

        result = self.agent_results[agent_id]
        result.status = "killed"
        result.output += f"\n\nAgent stopped: {reason}"

        # 清理
        self.active_agents.pop(agent_id, None)

        return result

    def get_agent_status(self, agent_id: str) -> Optional[AgentResult]:
        """
        获取智能体状态

        Args:
            agent_id: 智能体 ID

        Returns:
            智能体执行结果
        """
        return self.agent_results.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        列出所有智能体

        Returns:
            智能体列表
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
    发送消息工具

    向智能体发送消息以继续对话
    """

    def __init__(self, agent_tool: AgentTool):
        """
        初始化发送消息工具

        Args:
            agent_tool: 智能体工具实例
        """
        self.agent_tool = agent_tool

    async def send(
        self,
        agent_id: str,
        message: str
    ) -> AgentResult:
        """
        发送消息

        Args:
            agent_id: 智能体 ID
            message: 消息内容

        Returns:
            智能体执行结果
        """
        return await self.agent_tool.send_message(agent_id, message)


class TaskStopTool:
    """
    任务停止工具

    停止正在运行的智能体
    """

    def __init__(self, agent_tool: AgentTool):
        """
        初始化任务停止工具

        Args:
            agent_tool: 智能体工具实例
        """
        self.agent_tool = agent_tool

    async def stop(
        self,
        agent_id: str,
        reason: str = "User requested"
    ) -> AgentResult:
        """
        停止任务

        Args:
            agent_id: 智能体 ID
            reason: 停止原因

        Returns:
            智能体执行结果
        """
        return await self.agent_tool.stop_agent(agent_id, reason)


# 全局智能体工具实例
_global_agent_tool: Optional[AgentTool] = None


def get_agent_tool() -> AgentTool:
    """
    获取全局智能体工具实例

    Returns:
        智能体工具实例
    """
    global _global_agent_tool

    if _global_agent_tool is None:
        _global_agent_tool = AgentTool()

    return _global_agent_tool


# 工具注册
AGENT_TOOLS = {
    "Agent": AgentTool,
    "SendMessage": SendMessageTool,
    "TaskStop": TaskStopTool,
}
