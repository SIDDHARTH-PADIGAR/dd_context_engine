from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from dd_context_engine.config import settings
from dd_context_engine.context.compiler import ContextAssemblyService
from dd_context_engine.domain.schemas import (
    AssertionStatus,
    CommercialAssertion,
    ContextRequest,
    EvidenceSpan,
    RetrievalHit,
    WorkflowState,
)


class WorkflowRepo:
    async def get(self, tenant_id, case_id):
        return WorkflowState(
            case_id=case_id,
            tenant_id=tenant_id,
            stage="analysis",
            goal="inspect",
            model_version="model-1",
            prompt_version="prompt-1",
            updated_at=datetime.now(UTC),
        )


class AssertionRepo:
    def __init__(self, items):
        self.items = items

    async def find(self, tenant_id, entity_id, at_time, limit):
        return [
            assertion
            for assertion in self.items
            if assertion.tenant_id == tenant_id
            and assertion.entity_id == entity_id
        ][:limit]


class EvidenceRepo:
    def __init__(self, spans):
        self.spans = spans

    async def get_for_sources(self, tenant_id, source_ids, limit):
        allowed = set(source_ids)

        return [
            span
            for span in self.spans
            if span.tenant_id == tenant_id
            and span.source_id in allowed
        ][:limit]


class RetrievalRepo:
    def __init__(self, hits):
        self.hits = hits

    async def lexical_search(self, tenant_id, query, limit):
        return [
            hit
            for hit in self.hits
            if hit.tenant_id == tenant_id
        ][:limit]


@pytest.mark.asyncio
async def test_context_compiler_applies_configured_bounds_and_temporal_filter(
    monkeypatch,
):
    now = datetime.now(UTC)
    source = uuid4()

    monkeypatch.setattr(settings, "max_context_assertions", 2)
    monkeypatch.setattr(settings, "max_context_evidence", 1)

    assertions = [
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.08,
            recorded_at=now,
            valid_from=now - timedelta(days=1),
            source_id=source,
            extractor_name="x",
            extractor_version="1",
            status=AssertionStatus.ACTIVE,
        ),
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.10,
            recorded_at=now,
            valid_from=now - timedelta(days=1),
            source_id=source,
            extractor_name="x",
            extractor_version="2",
            status=AssertionStatus.ACTIVE,
        ),
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.05,
            recorded_at=now,
            valid_from=now - timedelta(days=1),
            source_id=source,
            extractor_name="x",
            extractor_version="3",
            status=AssertionStatus.SUPERSEDED,
        ),
    ]

    evidence = [
        EvidenceSpan(
            tenant_id="t1",
            source_id=source,
            start_offset=0,
            end_offset=12,
            text="Rate is 10%.",
        ),
        EvidenceSpan(
            tenant_id="t1",
            source_id=source,
            start_offset=13,
            end_offset=26,
            text="Rate is 8%.",
        ),
    ]

    service = ContextAssemblyService(
        WorkflowRepo(),
        AssertionRepo(assertions),
        EvidenceRepo(evidence),
    )

    bundle = await service.build(
        ContextRequest(
            tenant_id="t1",
            case_id="case-1",
            task="inspect",
            entity_id="v1",
            at_time=now,
            max_assertions=20,
            max_evidence_items=20,
        )
    )

    assert bundle.bounded is True
    assert len(bundle.assertions) == 2
    assert all(
        assertion.status != AssertionStatus.SUPERSEDED
        for assertion in bundle.assertions
    )
    assert len(bundle.evidence) == 1
    assert bundle.conflicts


@pytest.mark.asyncio
async def test_context_compiler_does_not_confuse_sequential_versions_with_conflicts():
    now = datetime.now(UTC)
    source = uuid4()

    assertions = [
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.08,
            recorded_at=now,
            valid_from=now - timedelta(days=10),
            valid_to=now - timedelta(days=5),
            source_id=source,
            extractor_name="x",
            extractor_version="1",
            status=AssertionStatus.HISTORICAL,
        ),
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.10,
            recorded_at=now,
            valid_from=now - timedelta(days=5),
            source_id=source,
            extractor_name="x",
            extractor_version="2",
            status=AssertionStatus.ACTIVE,
        ),
    ]

    service = ContextAssemblyService(
        WorkflowRepo(),
        AssertionRepo(assertions),
        EvidenceRepo([]),
    )

    bundle = await service.build(
        ContextRequest(
            tenant_id="t1",
            case_id="case-1",
            task="inspect",
            entity_id="v1",
            at_time=now,
        )
    )

    assert len(bundle.assertions) == 1
    assert bundle.assertions[0].value == 0.10
    assert bundle.conflicts == []


@pytest.mark.asyncio
async def test_context_compiler_can_retrieve_evidence_without_entity_id():
    source = uuid4()

    retrieval = RetrievalRepo(
        [
            RetrievalHit(
                span_id=uuid4(),
                tenant_id="t1",
                source_id=source,
                text="Funding rate is 10 percent.",
                score=0.91,
            ),
        ]
    )

    service = ContextAssemblyService(
        WorkflowRepo(),
        AssertionRepo([]),
        EvidenceRepo([]),
        retrieval=retrieval,
    )

    await service.build(
        ContextRequest(
            tenant_id="t1",
            case_id="case-1",
            task="What is the funding rate?",
        )
    )
    
@pytest.mark.asyncio
async def test_context_compiler_can_recover_historical_superseded_assertion():
    now = datetime.now(UTC)
    historical_time = now - timedelta(days=10)
    source = uuid4()

    assertions = [
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.10,
            recorded_at=now,
            valid_from=historical_time - timedelta(days=5),
            valid_to=historical_time + timedelta(days=5),
            source_id=source,
            extractor_name="x",
            extractor_version="1",
            status=AssertionStatus.SUPERSEDED,
        ),
        CommercialAssertion(
            tenant_id="t1",
            entity_id="v1",
            attribute="funding_rate",
            value=0.12,
            recorded_at=now,
            valid_from=historical_time + timedelta(days=6),
            source_id=source,
            extractor_name="x",
            extractor_version="2",
            status=AssertionStatus.ACTIVE,
        ),
    ]

    service = ContextAssemblyService(
        WorkflowRepo(),
        AssertionRepo(assertions),
        EvidenceRepo([]),
    )

    bundle = await service.build(
        ContextRequest(
            tenant_id="t1",
            case_id="case-1",
            task="What was the funding rate?",
            entity_id="v1",
            at_time=historical_time,
        )
    )

    assert len(bundle.assertions) == 1
    assert bundle.assertions[0].value == 0.10
