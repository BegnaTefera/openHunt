from __future__ import annotations


class DiscoveryError(RuntimeError):
    """A discovery source failed; other sources can still run."""


class QuotaExhaustedError(DiscoveryError):
    """The provider reported that its quota or rate limit is used up."""
