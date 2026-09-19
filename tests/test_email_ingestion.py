from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from dd_context_engine.ingestion.email import EmailIngestionService
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import EvidenceSpanRecord, SourceRecord
from dd_context_engine.storage.postgres import PostgresEvidenceRepository


@pytest.mark.asyncio
async def test_email_ingestion_persists_evidence_and_is_idempotent():
    tenant_id = f"email-integration-{uuid4()}"
    observed_at = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)

    raw_email = b"""\
From: buyer@example.com
To: seller@example.com
Subject: Funding terms
Message-ID: <funding-123@example.com>
In-Reply-To: <previous-456@example.com>
References: <root-789@example.com> <previous-456@example.com>
Date: Sat, 19 Sep 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

Funding rate is 10 percent.
"""

    repository = PostgresEvidenceRepository()
    service = EmailIngestionService(repository)

    try:
        first = await service.ingest(
            tenant_id=tenant_id,
            raw_email=raw_email,
            observed_at=observed_at,
        )

        second = await service.ingest(
            tenant_id=tenant_id,
            raw_email=raw_email,
            observed_at=observed_at,
        )

        assert first.source_id == second.source_id
        assert first.source_version == "<funding-123@example.com>"
        assert first.metadata["parent_id"] == "<previous-456@example.com>"
        assert first.metadata["references"] == [
            "<root-789@example.com>",
            "<previous-456@example.com>",
        ]

        async with session_factory() as session:
            sources = (
                await session.execute(
                    SourceRecord.__table__.select().where(
                        SourceRecord.tenant_id == tenant_id
                    )
                )
            ).all()

            spans = (
                await session.execute(
                    EvidenceSpanRecord.__table__.select().where(
                        EvidenceSpanRecord.tenant_id == tenant_id
                    )
                )
            ).all()

        assert len(sources) == 1
        assert len(spans) == 1
        assert spans[0].text == "Funding rate is 10 percent."
        assert spans[0].source_id == first.source_id

    finally:
        async with session_factory() as session:
            await session.execute(
                delete(EvidenceSpanRecord).where(
                    EvidenceSpanRecord.tenant_id == tenant_id
                )
            )
            await session.execute(
                delete(SourceRecord).where(
                    SourceRecord.tenant_id == tenant_id
                )
            )
            await session.commit()
            await engine.dispose()