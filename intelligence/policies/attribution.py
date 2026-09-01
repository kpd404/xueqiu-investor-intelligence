from collections.abc import Mapping


def current_author_text(content: str, raw_data: Mapping[str, object]) -> str:
    """Return only the current author's text from a normalized repost fact."""

    is_repost = raw_data.get("post_kind") == "REPOST" or isinstance(
        raw_data.get("retweeted_status"), Mapping
    )
    if not is_repost:
        return content

    # Xueqiu's normalized repost text uses the first ``//@`` marker to begin
    # the quoted status. Keep the original RawEvent content intact; this is a
    # derived attribution view used only by deterministic evidence policies.
    return content.split("//@", 1)[0].strip()
