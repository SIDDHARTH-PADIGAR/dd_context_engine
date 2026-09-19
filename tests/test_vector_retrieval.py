from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from dd_context_engine.domain.schemas import (
    EvidenceEmbedding,
    EvidenceEnvelope,
    EvidenceSpan,
    RetrievalHit,
)
from dd_context_engine.retrieval.hybrid import HybridRetrievalService
from dd_context_engine.retrieval.postgres import (
    PostgresEvidenceRepository,
    PostgresRetrievalRepository,
)
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import (
    EvidenceEmbeddingRecord,
    EvidenceSpanRecord,
    SourceRecord,
)


@pytest.mark.asyncio
async def test_semantic_retrieval_is_ranked_and_tenant_scoped():
    tenant_id = f"semantic-{uuid4()}"
    other_tenant_id = f"other-{uuid4()}"

    source_id = uuid4()
    other_source_id = uuid4()

    span_a = uuid4()
    span_b = uuid4()
    span_c = uuid4()
    other_span = uuid4()

    now = datetime.now(UTC)

    evidence_repo = PostgresEvidenceRepository()
    retrieval_repo = PostgresRetrievalRepository()

    envelope_a = EvidenceEnvelope(
        source_id=source_id,
        tenant_id=tenant_id,
        source_type="email",
        source_system="semantic-test",
        source_version="1",
        content_type="text/plain",
        content_uri="semantic://1",
        observed_at=now,
        ingested_at=now,
        checksum_sha256="a" * 64,
        permissions={"visibility": "tenant"},
    )

    envelope_b = EvidenceEnvelope(
        source_id=other_source_id,
        tenant_id=other_tenant_id,
        source_type="email",
        source_system="semantic-test",
        source_version="1",
        content_type="text/plain",
        content_uri="semantic://2",
        observed_at=now,
        ingested_at=now,
        checksum_sha256="b" * 64,
        permissions={"visibility": "tenant"},
    )

    spans = [
        EvidenceSpan(
            span_id=span_a,
            tenant_id=tenant_id,
            source_id=source_id,
            start_offset=0,
            end_offset=30,
            text="Funding rate is ten percent.",
        ),
        EvidenceSpan(
            span_id=span_b,
            tenant_id=tenant_id,
            source_id=source_id,
            start_offset=31,
            end_offset=60,
            text="Funding rate changed recently.",
        ),
        EvidenceSpan(
            span_id=span_c,
            tenant_id=tenant_id,
            source_id=source_id,
            start_offset=61,
            end_offset=90,
            text="Invoice payment is due monthly.",
        ),
        EvidenceSpan(
            span_id=other_span,
            tenant_id=other_tenant_id,
            source_id=other_source_id,
            start_offset=0,
            end_offset=30,
            text="Funding rate is ninety nine percent.",
        ),
    ]

    embeddings = [
        EvidenceEmbedding(
            tenant_id=tenant_id,
            span_id=span_a,
            model_name="test-embed",
            model_version="v1",
            dimensions=2,
            embedding=[1.0, 0.0],
        ),
        EvidenceEmbedding(
            tenant_id=tenant_id,
            span_id=span_b,
            model_name="test-embed",
            model_version="v1",
            dimensions=2,
            embedding=[0.9, 0.1],
        ),
        EvidenceEmbedding(
            tenant_id=tenant_id,
            span_id=span_c,
            model_name="test-embed",
            model_version="v1",
            dimensions=2,
            embedding=[0.0, 1.0],
        ),
        EvidenceEmbedding(
            tenant_id=other_tenant_id,
            span_id=other_span,
            model_name="test-embed",
            model_version="v1",
            dimensions=2,
            embedding=[1.0, 0.0],
        ),
    ]

    try:
        assert await evidence_repo.put_envelope(envelope_a) is True
        assert await evidence_repo.put_envelope(envelope_b) is True

        for span in spans:
            assert await evidence_repo.put_span(span) is True

        for embedding in embeddings:
            assert await retrieval_repo.put_embedding(embedding) is True

        assert (
            await retrieval_repo.put_embedding(embeddings[0])
            is False
        )

        results = await retrieval_repo.semantic_search(
            tenant_id=tenant_id,
            query_embedding=[1.0, 0.0],
            model_name="test-embed",
            model_version="v1",
            limit=10,
        )

        assert [result.span_id for result in results] == [
            span_a,
            span_b,
            span_c,
        ]

        assert results[0].score == pytest.approx(1.0)
        assert results[1].score > results[2].score

        other_results = await retrieval_repo.semantic_search(
            tenant_id=other_tenant_id,
            query_embedding=[1.0, 0.0],
            model_name="test-embed",
            model_version="v1",
            limit=10,
        )

        assert [result.span_id for result in other_results] == [
            other_span,
        ]

    finally:
        async with session_factory() as session:
            await session.execute(
                delete(EvidenceEmbeddingRecord).where(
                    EvidenceEmbeddingRecord.tenant_id.in_(
                        [tenant_id, other_tenant_id]
                    )
                )
            )
            await session.execute(
                delete(EvidenceSpanRecord).where(
                    EvidenceSpanRecord.tenant_id.in_(
                        [tenant_id, other_tenant_id]
                    )
                )
            )
            await session.execute(
                delete(SourceRecord).where(
                    SourceRecord.tenant_id.in_(
                        [tenant_id, other_tenant_id]
                    )
                )
            )
            await session.commit()
            await engine.dispose()


class FakeLexicalRepository:
    async def lexical_search(self, tenant_id, query, limit):
        return [
            RetrievalHit(
                span_id=uuid4(),
                tenant_id=tenant_id,
                source_id=uuid4(),
                text="lexical-first",
                score=0.9,
            ),
            RetrievalHit(
                span_id=uuid4(),
                tenant_id=tenant_id,
                source_id=uuid4(),
                text="lexical-second",
                score=0.8,
            ),
        ][:limit]


class FakeSemanticRepository:
    async def semantic_search(
        self,
        tenant_id,
        query_embedding,
        model_name,
        model_version,
        limit,
    ):
        return [
            RetrievalHit(
                span_id=uuid4(),
                tenant_id=tenant_id,
                source_id=uuid4(),
                text="semantic-first",
                score=0.95,
            ),
            RetrievalHit(
                span_id=uuid4(),
                tenant_id=tenant_id,
                source_id=uuid4(),
                text="semantic-second",
                score=0.85,
            ),
        ][:limit]


@pytest.mark.asyncio
async def test_hybrid_retrieval_returns_ranked_results():
    service = HybridRetrievalService(
        lexical=FakeLexicalRepository(),
        semantic=FakeSemanticRepository(),
    )

    results = await service.search(
        tenant_id="tenant-a",
        query="funding rate",
        query_embedding=[1.0, 0.0],
        model_name="test-embed",
        model_version="v1",
        limit=4,
    )

    assert len(results) == 4
    assert results[0].score >= results[-1].score