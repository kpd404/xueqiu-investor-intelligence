from contracts import AttentionLevel


def classify_attention(mention_count: int, conviction: float) -> AttentionLevel:
    """Minimal deterministic investor-level attention policy for the MVP."""

    if mention_count <= 0:
        return AttentionLevel.UNKNOWN
    if mention_count == 1:
        return AttentionLevel.DISCOVERED
    if mention_count <= 3:
        return AttentionLevel.TRACKING
    if conviction >= 70:
        return AttentionLevel.FOCUS
    return AttentionLevel.TRACKING
