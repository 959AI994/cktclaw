"""Compatibility facade for chip intent routing.

New code should use ``await resolve_chip_intent_async(...)`` or
``ChipIntentRouter.resolve_async(...)``. The legacy synchronous helpers do not
call the LLM; they only use deterministic fallback rules for old callers and CI.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .chip_intent_router import (
    ChipIntentRouter,
    build_chip_router_context,
    execution_skill_for_intent,
    get_chip_intent_router,
    intent_to_route_dict,
    resolve_chip_intent_async,
    resolve_chip_intent_rules,
)
from .schemas import (
    AgentCandidate,
    ArtifactQuery,
    ChipIntent,
    FallbackReason,
    RouteCandidate,
    SkillCandidate,
    ToolCandidate,
)


def resolve_chip_intent(text: str, context: Optional[Dict[str, Any]] = None) -> ChipIntent:
    """Legacy deterministic wrapper. Prefer ``resolve_chip_intent_async``."""
    return resolve_chip_intent_rules(text, context)


def detect_chip_design_intent(user_input: str) -> Optional[str]:
    """
    Legacy compatibility wrapper.

    Do not call LLM here. Prefer ``ChipIntentRouter.resolve_async()``.
    Returns an executable skill id only for deterministic execution routes;
    chip QA, clarification, and normal chat return ``None``.
    """
    intent = resolve_chip_intent_rules(user_input)
    if not intent.is_execution_route:
        return None
    return execution_skill_for_intent(intent)


def detect_chip_design_intent_with_confidence(user_input: str) -> Optional[dict]:
    """
    Legacy compatibility wrapper.

    Do not call LLM here. Prefer ``ChipIntentRouter.resolve_async()``.
    """
    intent = resolve_chip_intent_rules(user_input)
    return intent_to_route_dict(intent, user_input)


__all__ = [
    "AgentCandidate",
    "ArtifactQuery",
    "ChipIntent",
    "ChipIntentRouter",
    "FallbackReason",
    "build_chip_router_context",
    "RouteCandidate",
    "SkillCandidate",
    "ToolCandidate",
    "detect_chip_design_intent",
    "detect_chip_design_intent_with_confidence",
    "execution_skill_for_intent",
    "get_chip_intent_router",
    "intent_to_route_dict",
    "resolve_chip_intent",
    "resolve_chip_intent_async",
]
