from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    EvidenceEmbedding,
    EvidenceEnvelope,
    EvidenceSpan,
    RetrievalHit,
    WorkflowState,
)


class EvidenceRepository(Protocol):
    async def put_envelope(self, envelope: EvidenceEnvelope) -> bool: ...

    async def put_span(self, span: EvidenceSpan) -> bool: ...

    async def get_for_sources(
        self,
        tenant_id: str,
        source_ids: list[UUID],
        limit: int,
    ) -> list[EvidenceSpan]: ...


class AssertionRepository(Protocol):
    async def put(self, assertion: CommercialAssertion) -> bool: ...

    async def find(
        self,
        tenant_id: str,
        entity_id: str,
        at_time: datetime | None,
        limit: int,
    ) -> list[CommercialAssertion]: ...


class WorkflowRepository(Protocol):
    async def get(
        self,
        tenant_id: str,
        case_id: str,
    ) -> WorkflowState | None: ...

    async def put(self, state: WorkflowState) -> None: ...


class RetrievalRepository(Protocol):
    async def lexical_search(
        self,
        tenant_id: str,
        query: str,
        limit: int,
    ) -> list[RetrievalHit]: ...


class SemanticRepository(Protocol):
    async def put_embedding(
        self,
        embedding: EvidenceEmbedding,
    ) -> bool: ...

    async def semantic_search(
        self,
        tenant_id: str,
        query_embedding: list[float],
        model_name: str,
        model_version: str,
        limit: int,
    ) -> list[RetrievalHit]: ...


class RelationshipRepository(Protocol):
    async def related(
        self,
        tenant_id: str,
        entity_ids: list[str],
        limit: int,
    ) -> list[dict]: ...