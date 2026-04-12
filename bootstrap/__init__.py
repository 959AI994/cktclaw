"""
CktClaw Bootstrap - Project behavior loading and workspace initialization.
"""

from .workspace_parser import WorkspaceParser, ProjectBehavior, inject_project_behavior

__all__ = [
    "WorkspaceParser",
    "ProjectBehavior",
    "inject_project_behavior",
]
