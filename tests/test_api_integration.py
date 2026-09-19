from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from dd_context_engine.api.app import app
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import (
    AssertionRecord,
    EvidenceSpanRecord,
    SourceRecord,
    WorkflowStateRecord,
)
from sqlalchemy import delete


@pytest.mark.asyncio
async def test_api_end_to_end():
    tenant_id = f"api-integration-{uuid4()}"
    source_id = uuid4()
    span_id = uuid4()
    assertion_id = uuid4()
    case_id = f"case-{uuid4()}"
    now = datetime.now(timezone.utc)

    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            health = await client.get("/healthz")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            ready = await client.get("/readyz")
            assert ready.status_code == 200
            assert ready.json()["status"] == "ready"

            evidence = await client.post(
                "/v1/evidence",
                json={
                    "source_id": str(source_id),
                    "tenant_id": tenant_id,
                    "source_type": "email",
                    "source_system": "api-integration-test",
                    "source_version": "1",
                    "content_type": "text/plain",
                    "content_uri": "integration://api/email-1",
                    "observed_at": now.isoformat(),
                    "ingested_at": now.isoformat(),
                    "checksum_sha256": "b" * 64,
                    "metadata": {"subject": "Funding terms"},
                    "permissions": {"visibility": "tenant"},
                },
            )

            assert evidence.status_code == 202
            assert evidence.json() == {
                "source_id": str(source_id),
                "created": True,
            }

            span = await client.post(
                "/v1/evidence/spans",
                json={
                    "span_id": str(span_id),
                    "tenant_id": tenant_id,
                    "source_id": str(source_id),
                    "start_offset": 0,
                    "end_offset": 27,
                    "text": "Funding rate is 10 percent.",
                },
            )

            assert span.status_code == 202
            assert span.json() == {
                "span_id": str(span_id),
                "created": True,
            }

            assertion = await client.post(
                "/v1/assertions",
                json={
                    "assertion_id": str(assertion_id),
                    "tenant_id": tenant_id,
                    "entity_id": "vendor-1",
                    "attribute": "funding_rate",
                    "value": 0.10,
                    "recorded_at": now.isoformat(),
                    "status": "candidate",
                    "confidence": 0.99,
                    "source_id": str(source_id),
                    "evidence_span_id": str(span_id),
                    "extractor_name": "api-integration-test",
                    "extractor_version": "1",
                },
            )

            assert assertion.status_code == 202
            assert assertion.json() == {
                "assertion_id": str(assertion_id),
                "created": True,
            }

            context = await client.post(
                "/v1/context/compile",
                json={
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "task": "Determine the current funding rate",
                    "entity_id": "vendor-1",
                    "at_time": now.isoformat(),
                    "max_assertions": 10,
                    "max_evidence_items": 10,
                },
            )

            assert context.status_code == 200

            body = context.json()

            assert body["case_id"] == case_id
            assert body["task"] == "Determine the current funding rate"
            assert body["bounded"] is True
            assert len(body["assertions"]) == 1
            assert body["assertions"][0]["value"] == 0.10
            assert len(body["evidence"]) == 1
            assert body["evidence"][0]["text"] == "Funding rate is 10 percent."
            assert body["conflicts"] == []

    finally:
        async with session_factory() as session:
            await session.execute(
                delete(WorkflowStateRecord).where(
                    WorkflowStateRecord.tenant_id == tenant_id
                )
            )
            await session.execute(
                delete(AssertionRecord).where(
                    AssertionRecord.tenant_id == tenant_id
                )
            )
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