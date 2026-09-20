from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from dd_context_engine.config import settings
from dd_context_engine.domain.ports import (
    AssertionRepository,
    EvidenceRepository,
    RelationshipRepository,
    RetrievalRepository,
    SemanticRepository,
    WorkflowRepository,
)
from dd_context_engine.domain.schemas import (
    AssertionStatus,
    CommercialAssertion,
    ContextBundle,
    ContextRequest,
    EvidenceSpan,
)
from dd_context_engine.retrieval.hybrid import HybridRetrievalService


class ContextAssemblyService:
    """Construct a bounded working context from durable state and access paths."""

    def __init__(
        self,
        workflow: WorkflowRepository,
        assertions: AssertionRepository,
        evidence: EvidenceRepository,
        relationships: RelationshipRepository | None = None,
        retrieval: RetrievalRepository | None = None,
        semantic: SemanticRepository | None = None,
    ) -> None:
        self.workflow = workflow
        self.assertions = assertions
        self.evidence = evidence
        self.relationships = relationships
        self.retrieval = retrieval
        self.semantic = semantic

        self.hybrid = (
            HybridRetrievalService(
                lexical=retrieval,
                semantic=semantic,
            )
            if retrieval is not None and semantic is not None
            else None
        )

    async def build(self, request: ContextRequest) -> ContextBundle:
        workflow = await self.workflow.get(
            request.tenant_id,
            request.case_id,
        )

        assertion_limit = min(
            request.max_assertions,
            settings.max_context_assertions,
        )
        evidence_limit = min(
            request.max_evidence_items,
            settings.max_context_evidence,
        )

        assertions: list[CommercialAssertion] = []

        if request.entity_id:
            retrieved_assertions = await self.assertions.find(
                tenant_id=request.tenant_id,
                entity_id=request.entity_id,
                at_time=request.at_time,
                limit=assertion_limit,
            )

            assertions = [
                assertion
                for assertion in retrieved_assertions
                if self._relevant_to_context(
                    assertion,
                    request.at_time,
                )
            ][:assertion_limit]

        source_ids = list(
            dict.fromkeys(
                assertion.source_id
                for assertion in assertions
            )
        )

        source_evidence = await self.evidence.get_for_sources(
            tenant_id=request.tenant_id,
            source_ids=source_ids,
            limit=evidence_limit,
        )

        retrieved_evidence: list[EvidenceSpan] = []

        if request.query_embedding and self.hybrid:
            hits = await self.hybrid.search(
                tenant_id=request.tenant_id,
                query=request.task,
                query_embedding=request.query_embedding,
                model_name=request.embedding_model,
                model_version=request.embedding_version,
                limit=evidence_limit,
            )

            retrieved_evidence = [
                EvidenceSpan(
                    span_id=hit.span_id,
                    tenant_id=hit.tenant_id,
                    source_id=hit.source_id,
                    start_offset=0,
                    end_offset=len(hit.text),
                    text=hit.text,
                )
                for hit in hits
            ]

        elif self.retrieval:
            hits = await self.retrieval.lexical_search(
                tenant_id=request.tenant_id,
                query=request.task,
                limit=evidence_limit,
            )

            retrieved_evidence = [
                EvidenceSpan(
                    span_id=hit.span_id,
                    tenant_id=hit.tenant_id,
                    source_id=hit.source_id,
                    start_offset=0,
                    end_offset=len(hit.text),
                    text=hit.text,
                )
                for hit in hits
            ]

        evidence_by_id: dict[str, EvidenceSpan] = {}

        for span in retrieved_evidence + source_evidence:
            evidence_by_id[str(span.span_id)] = span

        evidence = list(evidence_by_id.values())[:evidence_limit]

        relationships: list[dict[str, Any]] = []

        if self.relationships and request.entity_id:
            relationships = await self.relationships.related(
                tenant_id=request.tenant_id,
                entity_ids=[request.entity_id],
                limit=evidence_limit * 4,
            )

        conflicts = self._conflicts(
            assertions,
            at_time=request.at_time,
        )

        return ContextBundle(
            case_id=request.case_id,
            task=request.task,
            workflow_state=workflow,
            assertions=assertions,
            evidence=evidence,
            relationships=relationships,
            conflicts=conflicts,
            bounded=(
                len(assertions) <= assertion_limit
                and len(evidence) <= evidence_limit
                and len(relationships) <= evidence_limit * 4
            ),
        )

    @staticmethod
    def _relevant_to_context(
        assertion: CommercialAssertion,
        at_time: datetime | None,
    ) -> bool:
        if at_time is None:
            return True

        if at_time is None and assertion.status in {
            AssertionStatus.SUPERSEDED,
            AssertionStatus.HISTORICAL,
        }:
            return False

        if (
            assertion.valid_from is not None
            and assertion.valid_from > at_time
        ):
            return False

        if (
            assertion.valid_to is not None
            and at_time >= assertion.valid_to
        ):
            return False

        return True

    @classmethod
    def _conflicts(
        cls,
        assertions: list[CommercialAssertion],
        at_time: datetime | None,
    ) -> list[dict[str, Any]]:
        relevant = [
            assertion
            for assertion in assertions
            if at_time is not None
            or assertion.status
            not in {
                AssertionStatus.SUPERSEDED,
                AssertionStatus.HISTORICAL,
            }
        ]

        grouped: dict[
            tuple[str, str, str | None, str],
            list[CommercialAssertion],
        ] = {}

        for assertion in relevant:
            key = (
                assertion.entity_id,
                assertion.attribute,
                assertion.unit,
                cls._canonical_json(assertion.scope),
            )

            grouped.setdefault(key, []).append(assertion)

        conflicts: list[dict[str, Any]] = []

        for (
            entity_id,
            attribute,
            unit,
            scope,
        ), items in grouped.items():
            conflicting: list[CommercialAssertion] = []

            for index, left in enumerate(items):
                if (
                    at_time is not None
                    and not cls._relevant_to_context(
                        left,
                        at_time,
                    )
                ):
                    continue

                for right in items[index + 1 :]:
                    if (
                        at_time is not None
                        and not cls._relevant_to_context(
                            right,
                            at_time,
                        )
                    ):
                        continue

                    if left.value == right.value:
                        continue

                    if not cls._intervals_overlap(left, right):
                        continue

                    conflicting.extend([left, right])

            if conflicting:
                unique_ids = list(
                    dict.fromkeys(
                        str(item.assertion_id)
                        for item in conflicting
                    )
                )

                conflicts.append(
                    {
                        "entity_id": entity_id,
                        "attribute": attribute,
                        "unit": unit,
                        "scope": json.loads(scope),
                        "assertion_ids": unique_ids,
                    }
                )

        return conflicts

    @staticmethod
    def _intervals_overlap(
        left: CommercialAssertion,
        right: CommercialAssertion,
    ) -> bool:
        starts = [
            value
            for value in (
                left.valid_from,
                right.valid_from,
            )
            if value is not None
        ]

        ends = [
            value
            for value in (
                left.valid_to,
                right.valid_to,
            )
            if value is not None
        ]

        latest_start = max(starts) if starts else None
        earliest_end = min(ends) if ends else None

        if latest_start is None or earliest_end is None:
            return (
                earliest_end is None
                or latest_start is None
                or latest_start < earliest_end
            )

        return latest_start < earliest_end

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )