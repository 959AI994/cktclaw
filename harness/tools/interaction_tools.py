"""
Interaction Tools - User Interaction Tools

Implements user interaction tools.

Core features:
1. AskUserQuestionTool - Ask user questions
2. BriefTool - Brief explanation
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class QuestionType(Enum):
    """Question type"""
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT_INPUT = "text_input"
    CONFIRMATION = "confirmation"


@dataclass
class QuestionOption:
    """Question option"""
    label: str
    description: str
    value: str


@dataclass
class Question:
    """Question"""
    question: str
    header: str
    options: List[QuestionOption]
    question_type: QuestionType = QuestionType.SINGLE_CHOICE
    multi_select: bool = False


@dataclass
class UserAnswer:
    """User answer"""
    question_id: str
    answer: str
    selected_options: Optional[List[str]] = None


class AskUserQuestionTool:
    """
    Ask user question tool

    Ask user questions during execution to get decisions
    """

    def __init__(self):
        """Initialize ask user question tool"""
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
        Ask user question

        Args:
            question: Question content
            header: Question title (short label, max 12 characters)
            options: Option list, each option contains label and description
            multi_select: Whether to allow multiple selection

        Returns:
            User's answer
        """
        # Generate question ID
        import uuid
        question_id = f"q-{uuid.uuid4().hex[:8]}"

        # Parse options
        question_options = []
        for opt in options:
            question_options.append(QuestionOption(
                label=opt["label"],
                description=opt["description"],
                value=opt.get("value", opt["label"])
            ))

        # Create question
        q = Question(
            question=question,
            header=header,
            options=question_options,
            question_type=QuestionType.MULTIPLE_CHOICE if multi_select else QuestionType.SINGLE_CHOICE,
            multi_select=multi_select
        )

        # Save question
        self.pending_questions[question_id] = q

        # Format question output
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

        # In actual implementation, should wait for user input
        # Now return formatted question
        return output

    def submit_answer(
        self,
        question_id: str,
        answer: str,
        selected_options: Optional[List[str]] = None
    ):
        """
        Submit user answer

        Args:
            question_id: Question ID
            answer: Answer content
            selected_options: Selected options (used for multiple selection)
        """
        user_answer = UserAnswer(
            question_id=question_id,
            answer=answer,
            selected_options=selected_options
        )

        self.answers[question_id] = user_answer

        # Remove pending question
        self.pending_questions.pop(question_id, None)

    def get_answer(self, question_id: str) -> Optional[UserAnswer]:
        """
        Get user answer

        Args:
            question_id: Question ID

        Returns:
            User answer
        """
        return self.answers.get(question_id)


class BriefTool:
    """
    Brief explanation tool

    Provide brief explanation or status update to user
    """

    @staticmethod
    async def brief(
        message: str,
        title: Optional[str] = None,
        level: str = "info"
    ) -> str:
        """
        Send brief explanation

        Args:
            message: Explanation content
            title: Title
            level: Level (info, warning, error, success)

        Returns:
            Formatted explanation
        """
        # Select icon
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
        }
        icon = icons.get(level, "ℹ️")

        # Format output
        output = f"\n{'-'*60}\n"
        if title:
            output += f"{icon} {title}\n"
            output += f"{'-'*60}\n"
        output += f"{message}\n"
        output += f"{'-'*60}\n"

        return output


# Global interaction tool instance
_global_ask_user_tool: Optional[AskUserQuestionTool] = None


def get_ask_user_tool() -> AskUserQuestionTool:
    """
    Get global ask user tool instance

    Returns:
        Ask user tool instance
    """
    global _global_ask_user_tool

    if _global_ask_user_tool is None:
        _global_ask_user_tool = AskUserQuestionTool()

    return _global_ask_user_tool


# Tool registration
INTERACTION_TOOLS = {
    "AskUserQuestion": AskUserQuestionTool,
    "Brief": BriefTool,
}
