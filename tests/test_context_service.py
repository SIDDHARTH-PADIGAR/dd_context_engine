from datetime import datetime, timezone
from uuid import uuid4

import pytest

from dd_context_engine.context.compiler import ContextAssemblyService
from dd_context_engine.domain.schemas import CommercialAssertion, ContextRequest, EvidenceSpan, WorkflowState


class WorkflowRepo:
    async def get(self, tenant_id, case_id):
        return WorkflowState(
            case_id=case_id, tenant_id=tenant_id, stage="analysis", goal="inspect",
            model_version="model-1", prompt_version="prompt-1", updated_at=datetime.now(timezone.utc)
        )


class AssertionRepo:
    def __init__(self, items):
        self.items = items

    async def find(self, tenant_id, entity_id, at_time, limit):
        return [a for a in self.items if a.tenant_id == tenant_id and a.entity_id == entity_id][:limit]


class EvidenceRepo:
    def __init__(self, spans):
        self.spans = spans

    async def get_for_sources(self, tenant_id, source_ids, limit):
        allowed = set(source_ids)
        return [s for s in self.spans if s.tenant_id == tenant_id and s.source_id in allowed][:limit]


@pytest.mark.asyncio
async def test_context_bundle_is_bounded_and_surfaces_conflict():
    now = datetime.now(timezone.utc)
    source = uuid4()
    assertions = [
        CommercialAssertion(
            tenant_id="t1", entity_id="v1", attribute="funding_rate", value=0.08,
            recorded_at=now, source_id=source, extractor_name="x", extractor_version="1"
        ),
        CommercialAssertion(
            tenant_id="t1", entity_id="v1", attribute="funding_rate", value=0.10,
            recorded_at=now, source_id=source, extractor_name="x", extractor_version="2"
        ),
    ]
    evidence = [EvidenceSpan(
        tenant_id="t1", source_id=source, start_offset=0, end_offset=12, text="Rate is 10%."
    )]
    service = ContextAssemblyService(WorkflowRepo(), AssertionRepo(assertions), EvidenceRepo(evidence))

    bundle = await service.build(ContextRequest(
        tenant_id="t1", case_id="case-1", task="inspect", entity_id="v1", max_assertions=2
    ))

    assert bundle.bounded
    assert len(bundle.assertions) == 2
    assert bundle.evidence
    assert bundle.conflicts
