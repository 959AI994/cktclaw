"""Tests for /model command syncing to ModelRouter."""
import pytest
from unittest.mock import MagicMock, patch


def test_model_switch_to_deepseek_calls_router():
    mock_router = MagicMock()
    mock_router.switch = MagicMock(return_value=True)
    with patch("cktclaw.handlers.model_handler.get_model_router",
               return_value=mock_router, create=True):
        from cktclaw.handlers.model_handler import _sync_router_after_switch
        _sync_router_after_switch("deepseek")
    mock_router.switch.assert_called_once_with("deepseek")


def test_model_switch_to_logicrt_does_not_call_router():
    mock_router = MagicMock()
    mock_router.switch = MagicMock(return_value=False)
    with patch("cktclaw.handlers.model_handler.get_model_router",
               return_value=mock_router, create=True):
        from cktclaw.handlers.model_handler import _sync_router_after_switch
        _sync_router_after_switch("logicrt")
    mock_router.switch.assert_not_called()


def test_model_switch_to_qwen_does_not_call_router():
    mock_router = MagicMock()
    with patch("cktclaw.handlers.model_handler.get_model_router",
               return_value=mock_router, create=True):
        from cktclaw.handlers.model_handler import _sync_router_after_switch
        _sync_router_after_switch("qwen")
    mock_router.switch.assert_not_called()


def test_router_sync_failure_is_non_fatal():
    with patch("cktclaw.handlers.model_handler.get_model_router",
               side_effect=RuntimeError("broken"), create=True):
        from cktclaw.handlers.model_handler import _sync_router_after_switch
        _sync_router_after_switch("deepseek")  # must not raise


def test_sync_helper_is_callable():
    from cktclaw.handlers import model_handler
    assert callable(getattr(model_handler, "_sync_router_after_switch", None))
