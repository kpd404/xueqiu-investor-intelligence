"""Source adapters that normalize external observations into raw events."""

from collectors.base import SourceAdapter
from collectors.manual import ManualImportAdapter
from collectors.xueqiu import XueqiuAdapter

__all__ = ["ManualImportAdapter", "SourceAdapter", "XueqiuAdapter"]
