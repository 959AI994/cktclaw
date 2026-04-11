"""
Interaction Tools - 用户交互工具

参考 Claude Code 的用户交互工具实现。

核心功能：
1. AskUserQuestionTool - 询问用户问题
2. BriefTool - 简要说明
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class QuestionType(Enum):
    """问题类型"""
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT_INPUT = "text_input"
    CONFIRMATION = "confirmation"


@dataclass
class QuestionOption:
    """问题选项"""
    label: str
    description: str
    value: str


@dataclass
class Question:
    """问题"""
    question: str
    header: str
    options: List[QuestionOption]
    question_type: QuestionType = QuestionType.SINGLE_CHOICE
    multi_select: bool = False


@dataclass
class UserAnswer:
    """用户回答"""
    question_id: str
    answer: str
    selected_options: Optional[List[str]] = None


class AskUserQuestionTool:
    """
    询问用户问题工具

    在执行过程中向用户提问以获取决策
    """

    def __init__(self):
        """初始化询问用户问题工具"""
        self.pending_questions: Dict[str, Question] = {}
        self.answers: Dict[str, UserAnswer] = {}

    async def ask(
        self,
        question: str,
        header: str,
        options: List[Dict[str, str]],
        multi_select: bool = False
    ) -> str:
        """
        询问用户问题

        Args:
            question: 问题内容
            header: 问题标题（简短标签，最多12字符）
            options: 选项列表，每个选项包含 label 和 description
            multi_select: 是否允许多选

        Returns:
            用户的回答
        """
        # 生成问题 ID
        import uuid
        question_id = f"q-{uuid.uuid4().hex[:8]}"

        # 解析选项
        question_options = []
        for opt in options:
            question_options.append(QuestionOption(
                label=opt["label"],
                description=opt["description"],
                value=opt.get("value", opt["label"])
            ))

        # 创建问题
        q = Question(
            question=question,
            header=header,
            options=question_options,
            question_type=QuestionType.MULTIPLE_CHOICE if multi_select else QuestionType.SINGLE_CHOICE,
            multi_select=multi_select
        )

        # 保存问题
        self.pending_questions[question_id] = q

        # 格式化问题输出
        output = f"\n{'='*60}\n"
        output += f"❓ {header}\n"
        output += f"{'='*60}\n\n"
        output += f"{question}\n\n"
        output += "Options:\n"
        for i, opt in enumerate(question_options, 1):
            output += f"  {i}. {opt.label}\n"
            output += f"     {opt.description}\n\n"

        if multi_select:
            output += "You can select multiple options.\n"

        output += f"\nQuestion ID: {question_id}\n"
        output += f"{'='*60}\n"

        # 在实际实现中，这里应该等待用户输入
        # 现在返回格式化的问题
        return output

    def submit_answer(
        self,
        question_id: str,
        answer: str,
        selected_options: Optional[List[str]] = None
    ):
        """
        提交用户回答

        Args:
            question_id: 问题 ID
            answer: 回答内容
            selected_options: 选中的选项（多选时使用）
        """
        user_answer = UserAnswer(
            question_id=question_id,
            answer=answer,
            selected_options=selected_options
        )

        self.answers[question_id] = user_answer

        # 移除待处理问题
        self.pending_questions.pop(question_id, None)

    def get_answer(self, question_id: str) -> Optional[UserAnswer]:
        """
        获取用户回答

        Args:
            question_id: 问题 ID

        Returns:
            用户回答
        """
        return self.answers.get(question_id)


class BriefTool:
    """
    简要说明工具

    向用户提供简要说明或状态更新
    """

    @staticmethod
    async def brief(
        message: str,
        title: Optional[str] = None,
        level: str = "info"
    ) -> str:
        """
        发送简要说明

        Args:
            message: 说明内容
            title: 标题
            level: 级别（info, warning, error, success）

        Returns:
            格式化的说明
        """
        # 选择图标
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
        }
        icon = icons.get(level, "ℹ️")

        # 格式化输出
        output = f"\n{'-'*60}\n"
        if title:
            output += f"{icon} {title}\n"
            output += f"{'-'*60}\n"
        output += f"{message}\n"
        output += f"{'-'*60}\n"

        return output


# 全局交互工具实例
_global_ask_user_tool: Optional[AskUserQuestionTool] = None


def get_ask_user_tool() -> AskUserQuestionTool:
    """
    获取全局询问用户工具实例

    Returns:
        询问用户工具实例
    """
    global _global_ask_user_tool

    if _global_ask_user_tool is None:
        _global_ask_user_tool = AskUserQuestionTool()

    return _global_ask_user_tool


# 工具注册
INTERACTION_TOOLS = {
    "AskUserQuestion": AskUserQuestionTool,
    "Brief": BriefTool,
}
