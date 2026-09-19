from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete

from dd_context_engine.context.compiler import ContextAssemblyService
from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    ContextRequest,
    EvidenceEnvelope,
    EvidenceSpan,
    WorkflowState,
)
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import (
    AssertionRecord,
    EvidenceSpanRecord,
    SourceRecord,
    WorkflowStateRecord,
)
from dd_context_engine.storage.postgres import (
    PostgresAssertionRepository,
    PostgresEvidenceRepository,
    PostgresWorkflowRepository,
)


@pytest.mark.asyncio
async def test_postgres_context_flow():
    tenant_id = f"integration-{uuid4()}"
    source_id = uuid4()
    span_id = uuid4()
    assertion_id = uuid4()
    case_id = f"case-{uuid4()}"
    now = datetime.now(timezone.utc)

    evidence_repo = PostgresEvidenceRepository()
    assertion_repo = PostgresAssertionRepository()
    workflow_repo = PostgresWorkflowRepository()

    envelope = EvidenceEnvelope(
        source_id=source_id,
        tenant_id=tenant_id,
        source_type="email",
        source_system="integration-test",
        source_version="1",
        content_type="text/plain",
        content_uri="integration://test/email-1",
        observed_at=now,
        ingested_at=now,
        checksum_sha256="a" * 64,
        metadata={"subject": "Funding terms"},
        permissions={"visibility": "tenant"},
    )

    span = EvidenceSpan(
        span_id=span_id,
        tenant_id=tenant_id,
        source_id=source_id,
        start_offset=0,
        end_offset=24,
        text="Funding rate is 10 percent.",
    )

    assertion = CommercialAssertion(
        assertion_id=assertion_id,
        tenant_id=tenant_id,
        entity_id="vendor-1",
        attribute="funding_rate",
        value=0.10,
        recorded_at=now,
        source_id=source_id,
        evidence_span_id=span_id,
        extractor_name="integration-test",
        extractor_version="1",
        confidence=0.99,
    )

    workflow = WorkflowState(
        case_id=case_id,
        tenant_id=tenant_id,
        stage="analysis",
        goal="Inspect funding terms",
        completed_steps=["ingestion"],
        pending_steps=["analysis"],
        model_version="test-model",
        prompt_version="test-prompt",
        updated_at=now,
    )

    try:
        assert await evidence_repo.put_envelope(envelope) is True
        assert await evidence_repo.put_span(span) is True
        assert await assertion_repo.put(assertion) is True
        await workflow_repo.put(workflow)

        stored_assertions = await assertion_repo.find(
            tenant_id=tenant_id,
            entity_id="vendor-1",
            at_time=now,
            limit=10,
        )

        assert len(stored_assertions) == 1
        assert stored_assertions[0].assertion_id == assertion_id
        assert stored_assertions[0].value == 0.10

        stored_workflow = await workflow_repo.get(
            tenant_id=tenant_id,
            case_id=case_id,
        )

        assert stored_workflow is not None
        assert stored_workflow.stage == "analysis"
        assert stored_workflow.goal == "Inspect funding terms"

        context_service = ContextAssemblyService(
            workflow=workflow_repo,
            assertions=assertion_repo,
            evidence=evidence_repo,
        )

        bundle = await context_service.build(
            ContextRequest(
                tenant_id=tenant_id,
                case_id=case_id,
                task="Determine the current funding rate",
                entity_id="vendor-1",
                at_time=now,
                max_assertions=10,
                max_evidence_items=10,
            )
        )

        assert bundle.bounded is True
        assert bundle.workflow_state is not None
        assert bundle.workflow_state.case_id == case_id
        assert len(bundle.assertions) == 1
        assert bundle.assertions[0].value == 0.10
        assert len(bundle.evidence) == 1
        assert bundle.evidence[0].text == "Funding rate is 10 percent."
        assert bundle.conflicts == []

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