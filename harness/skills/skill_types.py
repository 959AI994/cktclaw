"""
Skill Types - 技能类型定义

参考 src/skills/ 实现 Python 版本的技能系统。

核心职责：
1. 定义技能类型枚举（SkillType）
2. 定义技能定义结构（SkillDefinition）
3. 定义技能来源（LoadedFrom）
4. 提供技能元数据管理

设计原则：
- 技能资产化（可注册、可发现、可复用）
- 元数据驱动（name, description, whenToUse）
- 灵活执行（支持同步/异步、内联/fork）
- 权限控制（allowedTools, userInvocable）
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Callable, Awaitable
from pydantic import BaseModel, Field


class SkillType(str, Enum):
    """技能类型"""
    PROMPT = "prompt"           # Prompt 技能（最常见）
    TOOL = "tool"               # 工具技能
    WORKFLOW = "workflow"       # 工作流技能


class LoadedFrom(str, Enum):
    """技能来源"""
    BUNDLED = "bundled"                     # 内置技能
    USER_SETTINGS = "userSettings"          # 用户配置
    PROJECT_SETTINGS = "projectSettings"    # 项目配置
    POLICY_SETTINGS = "policySettings"      # 策略配置
    PLUGIN = "plugin"                       # 插件
    MCP = "mcp"                             # MCP 服务器
    COMMANDS_DEPRECATED = "commands_DEPRECATED"  # 旧版命令


class ExecutionContext(str, Enum):
    """执行上下文"""
    INLINE = "inline"   # 内联执行（默认）
    FORK = "fork"       # Fork 执行（独立进程）


class SkillDefinition(BaseModel):
    """
    技能定义

    包含技能的所有元数据和执行逻辑
    """
    # 基本信息
    name: str
    skill_type: SkillType = SkillType.PROMPT
    description: str
    display_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)

    # 使用指导
    when_to_use: Optional[str] = None
    argument_hint: Optional[str] = None
    argument_names: List[str] = Field(default_factory=list)

    # 权限与工具
    allowed_tools: List[str] = Field(default_factory=list)
    user_invocable: bool = True
    is_hidden: bool = False

    # 模型配置
    model: Optional[str] = None
    disable_model_invocation: bool = False

    # 执行配置
    execution_context: ExecutionContext = ExecutionContext.INLINE
    agent: Optional[str] = None
    effort: Optional[int] = None

    # 来源信息
    loaded_from: LoadedFrom = LoadedFrom.BUNDLED
    source: str = "bundled"
    skill_root: Optional[str] = None
    version: Optional[str] = None

    # 路径过滤（条件激活）
    paths: Optional[List[str]] = None

    # 内容
    content_length: int = 0
    markdown_content: Optional[str] = None

    # 钩子配置
    hooks: Optional[Dict[str, Any]] = None

    # 执行函数（可选）
    executor: Optional[Callable[[str, Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]] = None

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True

    def user_facing_name(self) -> str:
        """获取用户可见的技能名称"""
        return self.display_name or self.name

    def is_enabled(self) -> bool:
        """检查技能是否启用"""
        return not self.is_hidden

    async def get_prompt_for_command(
        self,
        args: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取技能的 Prompt 内容

        Args:
            args: 命令参数
            context: 执行上下文

        Returns:
            Prompt 内容块列表
        """
        if self.executor:
            return await self.executor(args, context or {})

        # 默认实现：返回 markdown 内容
        content = self.markdown_content or self.description

        # 替换参数占位符
        if args and self.argument_names:
            arg_values = args.split()
            for i, arg_name in enumerate(self.argument_names):
                if i < len(arg_values):
                    placeholder = f"${{{arg_name}}}"
                    content = content.replace(placeholder, arg_values[i])

        # 添加 skill root 前缀
        if self.skill_root:
            content = f"Base directory for this skill: {self.skill_root}\n\n{content}"

        return [{"type": "text", "text": content}]


def estimate_skill_frontmatter_tokens(skill: SkillDefinition) -> int:
    """
    估算技能前置元数据的 Token 数

    仅计算 name, description, whenToUse（不包括完整内容）
    """
    frontmatter_text = " ".join(
        filter(None, [skill.name, skill.description, skill.when_to_use])
    )
    # 粗估：1 token ≈ 4 chars
    return len(frontmatter_text) // 4
