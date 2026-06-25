"""Tests for PermissionManager + policy profiles."""
import pytest


def _pm(profile="default", **over):
    from cktclaw.runtime.permissions import PermissionManager
    policy = {
        "profiles": {
            "default":    {"allow_tools": ["*"], "deny_tools": [],
                           "allow_providers": ["*"]},
            "restricted": {"allow_tools": ["yosys", "abc", "opensta"],
                           "deny_tools": ["bash"], "allow_providers": ["local"]},
        }
    }
    policy["profiles"].update(over)
    return PermissionManager(policy=policy, active=profile)


def test_default_allows_all_tools():
    assert _pm().check_capability("yosys").allowed


def test_restricted_denies_bash():
    d = _pm("restricted").check_capability("bash")
    assert not d.allowed and "bash" in d.reason


def test_restricted_allows_listed_tool():
    assert _pm("restricted").check_capability("yosys").allowed


def test_restricted_blocks_cloud_provider():
    assert not _pm("restricted").check_provider("deepseek").allowed
    assert _pm("restricted").check_provider("local").allowed


def test_unknown_profile_falls_back_to_restricted():
    # safe-by-default: unknown profile must NOT be permissive
    from cktclaw.runtime.permissions import PermissionManager
    pm = PermissionManager(policy={"profiles": {}}, active="ghost")
    assert not pm.check_capability("bash").allowed


def test_capability_registry_exposes_required_permissions():
    from cktclaw.capability_registry import get_capability_registry
    reg = get_capability_registry()
    perms = reg.get_required_permissions("bash")
    assert isinstance(perms, (list, set, tuple))
