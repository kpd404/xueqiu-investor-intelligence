"""Deterministic, query-time Intelligence Attention Classification."""

from intelligence.attention_classification.rules import (
    AttentionClassificationDecision,
    AttentionClassificationFacts,
    classify_attention,
)
from intelligence.attention_classification.service import (
    IntelligenceAttentionClassificationService,
)

__all__ = [
    "AttentionClassificationDecision",
    "AttentionClassificationFacts",
    "IntelligenceAttentionClassificationService",
    "classify_attention",
]
