"""Tests for secure API credential loading."""
import pytest
from unittest.mock import patch


def test_get_deepseek_api_key_from_primary_env(monkeypatch):
    monkeypatch.setenv("CKTCLAW_DEEPSEEK_KEY", "sk-primary-test")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from cktclaw.api_credentials import get_deepseek_api_key
    assert get_deepseek_api_key(required=True) == "sk-primary-test"


def test_get_deepseek_api_key_from_fallback_env(monkeypatch):
    monkeypatch.delenv("CKTCLAW_DEEPSEEK_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fallback-test")
    from cktclaw.api_credentials import get_deepseek_api_key
    assert get_deepseek_api_key(required=True) == "sk-fallback-test"


def test_get_deepseek_api_key_primary_takes_precedence(monkeypatch):
    monkeypatch.setenv("CKTCLAW_DEEPSEEK_KEY", "sk-primary")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fallback")
    from cktclaw.api_credentials import get_deepseek_api_key
    assert get_deepseek_api_key() == "sk-primary"


def test_get_deepseek_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("CKTCLAW_DEEPSEEK_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with patch("cktclaw.api_credentials._resolve_from_yaml", return_value=None):
        from cktclaw.api_credentials import get_deepseek_api_key, CredentialError
        with pytest.raises(CredentialError, match="DeepSeek API key not found"):
            get_deepseek_api_key(required=True)


def test_get_deepseek_api_key_missing_optional_returns_none(monkeypatch):
    monkeypatch.delenv("CKTCLAW_DEEPSEEK_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with patch("cktclaw.api_credentials._resolve_from_yaml", return_value=None):
        from cktclaw.api_credentials import get_deepseek_api_key
        assert get_deepseek_api_key(required=False) is None


def test_config_deepseek_config_has_no_api_key():
    from cktclaw.config import DEEPSEEK_CONFIG
    assert "api_key" not in DEEPSEEK_CONFIG


def test_config_deepseek_config_has_required_non_secret_fields():
    from cktclaw.config import DEEPSEEK_CONFIG
    for field in ("base_url", "default_model", "timeout", "temperature", "max_tokens"):
        assert field in DEEPSEEK_CONFIG, f"Missing: {field}"


def test_deepseek_provider_uses_env_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-provider-test")
    import importlib
    import cktclaw.models.providers.deepseek_provider as mod
    importlib.reload(mod)
    provider = mod.DeepSeekProvider()
    assert provider._api_key == "sk-provider-test"
