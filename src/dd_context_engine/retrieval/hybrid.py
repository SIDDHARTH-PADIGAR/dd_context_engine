from __future__ import annotations

from dd_context_engine.domain.ports import (
    RetrievalRepository,
    SemanticRepository,
)
from dd_context_engine.domain.schemas import RetrievalHit


class HybridRetrievalService:
    """Fuse lexical and semantic rankings with Reciprocal Rank Fusion."""

    def __init__(
        self,
        lexical: RetrievalRepository,
        semantic: SemanticRepository,
        rrf_k: int = 60,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be >= 1")

        self.lexical = lexical
        self.semantic = semantic
        self.rrf_k = rrf_k

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        query_embedding: list[float],
        model_name: str,
        model_version: str,
        limit: int,
        candidate_limit: int | None = None,
    ) -> list[RetrievalHit]:
        if limit < 1:
            raise ValueError("limit must be >= 1")

        candidate_limit = candidate_limit or max(limit * 3, 10)

        lexical_hits = await self.lexical.lexical_search(
            tenant_id=tenant_id,
            query=query,
            limit=candidate_limit,
        )

        semantic_hits = await self.semantic.semantic_search(
            tenant_id=tenant_id,
            query_embedding=query_embedding,
            model_name=model_name,
            model_version=model_version,
            limit=candidate_limit,
        )

        scores: dict[str, float] = {}
        hits: dict[str, RetrievalHit] = {}

        for rank, hit in enumerate(lexical_hits, start=1):
            key = str(hit.span_id)
            hits[key] = hit
            scores[key] = scores.get(key, 0.0) + (
                1.0 / (self.rrf_k + rank)
            )

        for rank, hit in enumerate(semantic_hits, start=1):
            key = str(hit.span_id)
            hits[key] = hit
            scores[key] = scores.get(key, 0.0) + (
                1.0 / (self.rrf_k + rank)
            )

        ordered = sorted(
            hits.values(),
            key=lambda hit: (
                -scores[str(hit.span_id)],
                str(hit.span_id),
            ),
        )

        return [
            hit.model_copy(
                update={"score": scores[str(hit.span_id)]}
            )
            for hit in ordered[:limit]
        ]