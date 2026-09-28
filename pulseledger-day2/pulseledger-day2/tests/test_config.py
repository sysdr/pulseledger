"""Stripe test-mode guard and the lifecycle's transition rules."""
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.lifecycle import IllegalTransition, Lifecycle, ServiceState


def test_live_stripe_key_is_refused():
    with pytest.raises(ValidationError, match="live Stripe key refused"):
        Settings(stripe_secret_key="sk_live_" + "x" * 24)


def test_live_restricted_key_is_refused():
    with pytest.raises(ValidationError, match="live Stripe key refused"):
        Settings(stripe_secret_key="rk_live_" + "x" * 24)


def test_test_key_is_accepted_and_kept_secret():
    s = Settings(stripe_secret_key="sk_test_" + "x" * 24)
    assert s.stripe_mode == "test"
    assert "sk_test_" not in repr(s)


def test_empty_key_means_unset():
    assert Settings(stripe_secret_key="").stripe_mode == "unset"


def test_stopping_is_terminal():
    lc = Lifecycle()
    lc.move_to(ServiceState.READY)
    lc.move_to(ServiceState.STOPPING)
    with pytest.raises(IllegalTransition):
        lc.move_to(ServiceState.READY)
