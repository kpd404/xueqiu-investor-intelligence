"""Backward-compatible import for the generic OpenAI-compatible adapter."""

from ai.extractors.openai_compatible import OpenAICompatibleOpinionExtractor

OpenAIOpinionExtractor = OpenAICompatibleOpinionExtractor

__all__ = ["OpenAIOpinionExtractor"]
