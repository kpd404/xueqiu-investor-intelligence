from intelligence.policies.attribution import current_author_text


def test_non_repost_content_is_current_author_text() -> None:
    content = "作者自己的文本 //@这不是一条转发"

    assert current_author_text(content, {}) == content


def test_repost_content_stops_before_quoted_marker() -> None:
    content = "作者自己的文本//@原作者:被转发的证券观点"

    assert current_author_text(content, {"post_kind": "REPOST"}) == "作者自己的文本"


def test_nested_repost_marker_is_not_scanned_as_current_author_text() -> None:
    content = "回复作者:赞同//@原作者:腾讯继续看多"

    assert (
        current_author_text(
            content,
            {"retweeted_status": {"id": "nested-1"}},
        )
        == "回复作者:赞同"
    )
