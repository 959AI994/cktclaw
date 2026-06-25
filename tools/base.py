"""
BaseTool — abstract base class for all CktClaw tools.

Every tool (EDA, system, agent) must implement this interface.
Tools describe themselves via JSON Schema and execute asynchronously.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolContext:
    """Context passed to tool execution."""
    session_id: str = ""
    working_dir: str = ""
    user_id: str = ""
    # EDA-specific context
    design_name: Optional[str] = None
    target_library: Optional[str] = None
    # Populated by the runtime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # For tools that produce files
    artifacts: List[str] = field(default_factory=list)

    @classmethod
    def ok(cls, output: str, **kwargs) -> "ToolResult":
        return cls(success=True, output=output, **kwargs)

    @classmethod
    def fail(cls, error: str, output: str = "", **kwargs) -> "ToolResult":
        return cls(success=False, output=output, error=error, **kwargs)


class BaseTool(ABC):
    """
    Abstract base class for all CktClaw tools.

    Subclasses must define:
      - name: unique tool identifier
      - description: natural language description for LLM
      - parameters: JSON Schema dict describing input parameters
      - execute(): async implementation

    Optional overrides:
      - read_only: if True, tool can run in parallel (default: False)
      - category: grouping for UI display
      - requires: list of system requirements (e.g., ["yosys", "opensta"])
    """

    # Must be set by subclass
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    # Optional
    read_only: bool = False
    category: str = "general"
    requires: List[str] = []

    @abstractmethod
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            params: Validated parameters matching self.parameters schema.
            context: Execution context (session, working dir, etc.)

        Returns:
            ToolResult with success/failure and output.
        """
        ...

    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """
        Validate parameters against schema. Returns error message or None.

        Default implementation checks required fields.
        """
        required = self.parameters.get("required", [])
        properties = self.parameters.get("properties", {})

        for field_name in required:
            if field_name not in params:
                return f"Missing required parameter: {field_name}"

        # Type checking for provided params
        for key, value in params.items():
            if key not in properties:
                continue
            prop_schema = properties[key]
            expected_type = prop_schema.get("type")
            if expected_type == "string" and not isinstance(value, str):
                return f"Parameter '{key}' must be a string"
            elif expected_type == "integer" and not isinstance(value, int):
                return f"Parameter '{key}' must be an integer"
            elif expected_type == "boolean" and not isinstance(value, bool):
                return f"Parameter '{key}' must be a boolean"
            elif expected_type == "array" and not isinstance(value, list):
                return f"Parameter '{key}' must be an array"

        return None

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Convert to Anthropic tool_use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def __repr__(self) -> str:
        return f"<Tool:{self.name} category={self.category} read_only={self.read_only}>"
