from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from dd_context_engine.domain.schemas import (
    EvidenceEnvelope,
    EvidenceSpan,
)
from dd_context_engine.retrieval.postgres import PostgresRetrievalRepository
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import EvidenceSpanRecord, SourceRecord
from dd_context_engine.storage.postgres import PostgresEvidenceRepository


@pytest.mark.asyncio
async def test_lexical_retrieval_is_ranked_and_tenant_scoped():
    tenant_id = f"retrieval-{uuid4()}"
    other_tenant_id = f"other-{uuid4()}"

    source_id = uuid4()
    other_source_id = uuid4()

    span_id = uuid4()
    generic_span_id = uuid4()
    other_span_id = uuid4()

    now = datetime.now(UTC)

    evidence_repo = PostgresEvidenceRepository()
    retrieval_repo = PostgresRetrievalRepository()

    envelope = EvidenceEnvelope(
        source_id=source_id,
        tenant_id=tenant_id,
        source_type="email",
        source_system="retrieval-test",
        source_version="1",
        content_type="text/plain",
        content_uri="retrieval://email/1",
        observed_at=now,
        ingested_at=now,
        checksum_sha256="a" * 64,
        metadata={},
        permissions={"visibility": "tenant"},
    )

    other_envelope = EvidenceEnvelope(
        source_id=other_source_id,
        tenant_id=other_tenant_id,
        source_type="email",
        source_system="retrieval-test",
        source_version="1",
        content_type="text/plain",
        content_uri="retrieval://email/2",
        observed_at=now,
        ingested_at=now,
        checksum_sha256="b" * 64,
        metadata={},
        permissions={"visibility": "tenant"},
    )

    spans = [
        EvidenceSpan(
            span_id=span_id,
            tenant_id=tenant_id,
            source_id=source_id,
            start_offset=0,
            end_offset=50,
            text="The revised funding rate is 10 percent.",
        ),
        EvidenceSpan(
            span_id=generic_span_id,
            tenant_id=tenant_id,
            source_id=source_id,
            start_offset=51,
            end_offset=90,
            text="Payment terms are net thirty days.",
        ),
        EvidenceSpan(
            span_id=other_span_id,
            tenant_id=other_tenant_id,
            source_id=other_source_id,
            start_offset=0,
            end_offset=45,
            text="The funding rate is 99 percent.",
        ),
    ]

    try:
        assert await evidence_repo.put_envelope(envelope) is True
        assert await evidence_repo.put_envelope(other_envelope) is True

        for span in spans:
            assert await evidence_repo.put_span(span) is True

        results = await retrieval_repo.lexical_search(
            tenant_id=tenant_id,
            query="funding rate",
            limit=10,
        )

        assert len(results) == 1
        assert results[0].span_id == span_id
        assert results[0].source_id == source_id
        assert results[0].tenant_id == tenant_id
        assert results[0].score > 0

        other_results = await retrieval_repo.lexical_search(
            tenant_id=other_tenant_id,
            query="funding rate",
            limit=10,
        )

        assert len(other_results) == 1
        assert other_results[0].span_id == other_span_id

    finally:
        async with session_factory() as session:
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