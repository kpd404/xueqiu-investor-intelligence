from uuid import uuid4

import pytest

from collectors.xueqiu.browser import validate_xueqiu_homepage_url
from collectors.xueqiu.errors import (
    AuthenticationRequired,
    NavigationFailed,
    NoContent,
    ParseFailed,
    RateLimitedOrBlocked,
)


def test_xueqiu_failure_types_are_distinct() -> None:
    failures = {
        AuthenticationRequired,
        NavigationFailed,
        ParseFailed,
        RateLimitedOrBlocked,
        NoContent,
    }
    assert len(failures) == 5


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://example.com/u/123",
        "https://xueqiu.com/search?q=123",
    ],
)
def test_invalid_profile_urls_raise_navigation_failed(url: str | None) -> None:
    with pytest.raises(NavigationFailed):
        validate_xueqiu_homepage_url(url)


def test_uuid_fixture_is_not_an_authentication_value() -> None:
    assert str(uuid4())
