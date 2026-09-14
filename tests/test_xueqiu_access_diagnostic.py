from collectors.xueqiu.access_diagnostic import (
    ResponseDiagnostic,
    classify_block_detection,
    safe_body_summary,
    safe_url,
)


def test_safe_summary_does_not_return_response_body_or_query() -> None:
    body = "private-feed-text 滑动验证 and token=secret-value"

    length, fingerprint, markers = safe_body_summary(body)

    assert length == len(body)
    assert len(fingerprint) == 16
    assert "private-feed-text" not in fingerprint
    assert "token=secret-value" not in markers
    assert "BLOCKED_MARKER:滑动验证" in markers
    assert safe_url("https://xueqiu.com/u/1?token=secret#fragment") == "https://xueqiu.com/u/1"


def test_block_source_distinguishes_http_and_page_signals() -> None:
    response = ResponseDiagnostic(
        host="xueqiu.com",
        path="/v4/statuses/home_timeline.json",
        method="GET",
        status=429,
        content_type="application/json",
        body_length=12,
        body_fingerprint="fingerprint",
        safe_markers=(),
        following_candidate=False,
        parsed_item_count=None,
        parser_error_type=None,
        redirect_depth=0,
    )

    sources = classify_block_detection(
        responses=(response,),
        page_safe_markers=("BLOCKED_MARKER:访问受限",),
        page_title="验证",
        accepted_following_payload_count=0,
    )

    assert sources == (
        "HTTP_STATUS",
        "PAGE_BODY_MARKER",
        "PAGE_TITLE_MARKER",
        "NO_ACCEPTED_FOLLOWING_RESPONSE",
    )


def test_no_block_marker_is_not_classified_as_access_block() -> None:
    response = ResponseDiagnostic(
        host="xueqiu.com",
        path="/v4/statuses/home_timeline.json",
        method="GET",
        status=200,
        content_type="application/json",
        body_length=2,
        body_fingerprint="fingerprint",
        safe_markers=(),
        following_candidate=False,
        parsed_item_count=None,
        parser_error_type="INVALID_JSON",
        redirect_depth=0,
    )

    sources = classify_block_detection(
        responses=(response,),
        page_safe_markers=(),
        page_title="雪球",
        accepted_following_payload_count=0,
    )

    assert sources == ("NO_ACCEPTED_FOLLOWING_RESPONSE",)
