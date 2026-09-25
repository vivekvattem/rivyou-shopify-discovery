"""Provider-neutral discovery contracts."""

from __future__ import annotations

from typing import Protocol

from rivyou.models import CandidateRecord


class DiscoveryProvider(Protocol):
    name: str

    async def discover(self, limit: int | None = None) -> list[CandidateRecord]:
        """Return normalized candidate leads with provenance; never imply verification."""
        ...

