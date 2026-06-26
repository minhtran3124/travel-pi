import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_prod_wildcard_with_credentials_rejected():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            cors_origins=["*"],
            cors_allow_credentials=True,
        )


def test_prod_explicit_origins_ok():
    s = Settings(
        environment="production",
        cors_origins=["https://app.example.com"],
        cors_allow_credentials=True,
    )
    assert s.is_production


def test_dev_wildcard_ok():
    s = Settings(
        environment="development",
        cors_origins=["*"],
        cors_allow_credentials=True,
    )
    assert not s.is_production
