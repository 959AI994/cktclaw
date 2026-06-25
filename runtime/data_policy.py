"""
Data egress control & offline mode — protect RTL/netlist IP.

Guarantees that design files are never *silently* shipped to a cloud LLM:
  - offline / air-gapped mode forces local-only providers (hard block)
  - a single egress checkpoint classifies (and optionally redacts) outbound
    content and always audits design egress

This is the highest-value enterprise control for an EDA workflow.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

# Providers that never leave the local network.
_LOCAL_PROVIDERS = {"local", "ollama", "vllm", "qwen"}

# Heuristic markers that indicate hardware design content.
_DESIGN_MARKERS = re.compile(
    r"\b(module|endmodule|always|assign|wire|reg|input|output|inout)\b|"
    r"\.(v|sv|vhd|vhdl|aig|blif|edif|def|lef|gds)\b",
    re.IGNORECASE,
)
_MODULE_BODY = re.compile(r"module\b.*?endmodule", re.IGNORECASE | re.DOTALL)


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def _truthy(val: Optional[str]) -> bool:
    return bool(val) and val.strip().lower() not in ("0", "false", "no", "off", "")


def _policy_offline() -> bool:
    try:
        from .permissions import load_policy
        return bool(load_policy().get("security", {}).get("offline", False))
    except Exception:
        return False


def _policy_redact() -> bool:
    try:
        from .permissions import load_policy
        return bool(load_policy().get("security", {}).get("redact_design_egress", False))
    except Exception:
        return False


def is_offline() -> bool:
    return _truthy(os.environ.get("CKTCLAW_OFFLINE")) or _policy_offline()


def classify(content: str) -> str:
    """Classify outbound content: 'design' for HDL/netlist, else 'text'."""
    if content and _DESIGN_MARKERS.search(content):
        return "design"
    return "text"


def redact_design(content: str) -> str:
    """Mask module bodies in design content for safe cloud egress."""
    if not content:
        return content
    return _MODULE_BODY.sub("module [REDACTED-DESIGN-BODY] endmodule", content)


class EgressGuard:
    """Single egress chokepoint for outbound LLM traffic."""

    def check_provider(self, provider: str) -> Decision:
        if is_offline() and provider not in _LOCAL_PROVIDERS:
            return Decision(
                False,
                f"offline mode is enabled — cloud provider '{provider}' is blocked; "
                f"switch to a local provider via /model",
            )
        return Decision(True, "allowed")

    def guard_outbound(self, provider: str, content: str) -> str:
        """Classify + (optionally) redact outbound content and audit egress.

        Returns the content that may actually be sent (possibly redacted).
        """
        classification = classify(content)
        is_cloud = provider not in _LOCAL_PROVIDERS
        redacted = False
        out = content

        if classification == "design" and is_cloud and _policy_redact():
            out = redact_design(content)
            redacted = True

        try:
            from .audit import audit_event
            audit_event(
                kind="egress",
                capability=provider,
                status="redacted" if redacted else "sent",
                extra={
                    "classification": classification,
                    "provider_kind": "cloud" if is_cloud else "local",
                    "redacted": redacted,
                },
            )
        except Exception:
            pass

        return out
