"""
PermissionManager — config-driven policy profiles (RBAC-light for single-user CLI).

A policy declares named profiles controlling allowed/denied capabilities (glob
match on tool names) and allowed LLM providers. ``CapabilityRegistry.execute()``
consults the manager before running anything; denials are audited.

Safe-by-default: an unknown / missing active profile resolves to the most
restrictive known profile, never ``allow *``.
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Used when no profile can be resolved at all.
_SAFE_DENY: Dict[str, Any] = {
    "allow_tools": [],
    "deny_tools": ["*"],
    "allow_providers": [],
}


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def _matches_any(name: str, patterns) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in (patterns or []))


class PermissionManager:
    def __init__(self, policy: Optional[Dict[str, Any]] = None, active: Optional[str] = None):
        self._policy = policy or {}
        self._profiles: Dict[str, Any] = self._policy.get("profiles", {}) or {}
        self._active_name = active or os.environ.get("CKTCLAW_PROFILE") or "default"
        self._profile = self._resolve_profile(self._active_name)

    def _resolve_profile(self, name: str) -> Dict[str, Any]:
        if name in self._profiles:
            return self._profiles[name]
        # Safe-by-default fallback: prefer a known restrictive profile.
        for candidate in ("restricted", "ci"):
            if candidate in self._profiles:
                return self._profiles[candidate]
        return _SAFE_DENY

    @property
    def active_profile(self) -> str:
        return self._active_name

    def check_capability(self, name: str) -> Decision:
        deny = self._profile.get("deny_tools", [])
        allow = self._profile.get("allow_tools", [])
        if _matches_any(name, deny):
            return Decision(False, f"capability '{name}' is denied by profile "
                                   f"'{self._active_name}'")
        if _matches_any(name, allow):
            return Decision(True, "allowed")
        return Decision(False, f"capability '{name}' not in allow-list for profile "
                               f"'{self._active_name}'")

    def check_provider(self, name: str) -> Decision:
        # Offline mode overrides the profile: only local providers are allowed.
        try:
            from .data_policy import is_offline, _LOCAL_PROVIDERS
            if is_offline() and name not in _LOCAL_PROVIDERS:
                return Decision(False, f"offline mode — provider '{name}' is blocked")
        except Exception:
            pass
        allow = self._profile.get("allow_providers", [])
        if _matches_any(name, allow):
            return Decision(True, "allowed")
        return Decision(False, f"provider '{name}' not allowed by profile "
                               f"'{self._active_name}'")


_DEFAULT_POLICY_PATH = Path(__file__).parent / "policy.default.yaml"
_USER_POLICY_PATH = Path.home() / ".cktclaw" / "policy.yaml"

_permission_manager: Optional[PermissionManager] = None


def load_policy() -> Dict[str, Any]:
    """Load the policy dict: ~/.cktclaw/policy.yaml → packaged default."""
    import yaml

    for path in (_USER_POLICY_PATH, _DEFAULT_POLICY_PATH):
        try:
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("profiles"):
                    return data
        except Exception:
            continue
    return {"profiles": {}}


def get_permission_manager() -> PermissionManager:
    """Return the process-wide PermissionManager (lazy singleton)."""
    global _permission_manager
    if _permission_manager is None:
        active = os.environ.get("CKTCLAW_PROFILE")
        _permission_manager = PermissionManager(policy=load_policy(), active=active)
    return _permission_manager
