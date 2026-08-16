import pytest

from ownerrez_mcp.config import Settings


@pytest.fixture
def oauth_settings():
    return Settings(access_token="SECRET-OAUTH-TOKEN", max_retries=2, timeout=5.0)


@pytest.fixture
def pat_settings():
    return Settings(username="me@example.com", token="SECRET-PAT", max_retries=2, timeout=5.0)
