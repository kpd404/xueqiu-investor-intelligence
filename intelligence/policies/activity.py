"""Shared predicates for existing multi-investor activity semantics."""


def has_multi_investor_activity(investor_count: int, *, threshold: int) -> bool:
    if threshold < 2:
        raise ValueError("multi-investor threshold must be at least 2")
    return investor_count >= threshold


__all__ = ["has_multi_investor_activity"]
