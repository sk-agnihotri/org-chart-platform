from __future__ import annotations

from typing import Any, Protocol


class EnrichmentProvider(Protocol):
    def normalize_title(self, raw_title: str) -> dict[str, Any]: ...

    def rank_candidates(self, employee: dict, candidates: list[dict]) -> list[str]: ...


class DisabledEnrichment:
    enabled = False

    def normalize_title(self, raw_title: str) -> dict[str, Any]:
        raise RuntimeError("LLM enrichment is disabled")

    def rank_candidates(self, employee: dict, candidates: list[dict]) -> list[str]:
        raise RuntimeError("LLM enrichment is disabled")
