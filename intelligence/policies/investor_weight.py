DEFAULT_QUALITY_SCORE = 50.0


def investor_weight(quality_score: float | None) -> tuple[float, float]:
    """Return the effective quality score and its normalized V0 weight."""

    effective_score = DEFAULT_QUALITY_SCORE if quality_score is None else quality_score
    effective_score = min(100.0, max(0.0, float(effective_score)))
    return effective_score, effective_score / 100.0
