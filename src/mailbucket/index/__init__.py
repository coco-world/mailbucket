"""Persistent per-source SQLite search indexes."""

from mailbucket.index.manager import (
    IndexedMatch,
    IndexInfo,
    IndexManager,
    IndexProgress,
    IndexState,
)

__all__ = ["IndexInfo", "IndexManager", "IndexProgress", "IndexState", "IndexedMatch"]
