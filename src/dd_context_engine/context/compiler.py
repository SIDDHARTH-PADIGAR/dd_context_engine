from __future__ import annotations

from dd_context_engine.domain.ports import (
    AssertionRepository,
    EvidenceRepository,
    RelationshipRepository,
    WorkflowRepository,
)
from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    ContextBundle,
    ContextRequest,
)


class ContextAssemblyService:
    """Construct a bounded working context from durable state and access paths."""

    def __init__(
        self,
        workflow: WorkflowRepository,
        assertions: AssertionRepository,
        evidence: EvidenceRepository,
        relationships: RelationshipRepository | None = None,
    ) -> None:
        self.workflow = workflow
        self.assertions = assertions
        self.evidence = evidence
        self.relationships = relationships

    async def build(self, request: ContextRequest) -> ContextBundle:
        workflow = await self.workflow.get(request.tenant_id, request.case_id)
        assertions: list[CommercialAssertion] = []
        if request.entity_id:
            assertions = await self.assertions.find(
                tenant_id=request.tenant_id,
                entity_id=request.entity_id,
                at_time=request.at_time,
                limit=request.max_assertions,
            )

        source_ids = list(dict.fromkeys(a.source_id for a in assertions))
        evidence = await self.evidence.get_for_sources(
            tenant_id=request.tenant_id,
            source_ids=source_ids,
            limit=request.max_evidence_items,
        )

        relationships = []
        if self.relationships and request.entity_id:
            relationships = await self.relationships.related(
                tenant_id=request.tenant_id,
                entity_ids=[request.entity_id],
                limit=request.max_evidence_items * 4,
            )

        conflicts = self._conflicts(assertions)
        return ContextBundle(
            case_id=request.case_id,
            task=request.task,
            workflow_state=workflow,
            assertions=assertions,
            evidence=evidence,
            relationships=relationships,
            conflicts=conflicts,
            bounded=True,
        )

    @staticmethod
    def _conflicts(assertions: list[CommercialAssertion]) -> list[dict]:
        grouped: dict[tuple[str, str], list[CommercialAssertion]] = {}
        for assertion in assertions:
            grouped.setdefault((assertion.entity_id, assertion.attribute), []).append(assertion)

        conflicts = []
        for (entity_id, attribute), items in grouped.items():
            if len({repr(item.value) for item in items}) > 1:
                conflicts.append(
                    {
                        "entity_id": entity_id,
                        "attribute": attribute,
                        "assertion_ids": [str(item.assertion_id) for item in items],
                    }
                )
        return conflicts
