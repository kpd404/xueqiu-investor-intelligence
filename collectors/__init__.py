"""Source adapters that normalize external observations into raw events."""

from collectors.base import SourceAdapter
from collectors.manual import ManualImportAdapter

__all__ = ["ManualImportAdapter", "SourceAdapter"]
