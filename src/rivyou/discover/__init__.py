"""Candidate ingestion helpers."""

from .manager import DiscoveryManager
from .seeds import load_candidates

__all__ = ["DiscoveryManager", "load_candidates"]
