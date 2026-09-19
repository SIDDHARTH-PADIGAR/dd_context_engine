from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    EvidenceEmbedding,
    EvidenceEnvelope,
    EvidenceSpan,
    RetrievalHit,
    WorkflowState,
)
from dd_context_engine.storage.db import session_factory
from dd_context_engine.storage.models import (
    AssertionRecord,
    EvidenceEmbeddingRecord,
    EvidenceSpanRecord,
    SourceRecord,
    WorkflowStateRecord,
)


class PostgresEvidenceRepository:
    async def put_envelope(self, envelope: EvidenceEnvelope) -> bool:
        values = envelope.model_dump()
        values["metadata_"] = values.pop("metadata")

        async with session_factory() as session:
            stmt = insert(SourceRecord).values(**values).on_conflict_do_nothing(
                constraint="uq_source_tenant_id"
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount)

    async def put_span(self, span: EvidenceSpan) -> bool:
        values = span.model_dump()

        async with session_factory() as session:
            stmt = insert(EvidenceSpanRecord).values(**values).on_conflict_do_nothing(
                constraint="uq_span_tenant_id"
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount)

    async def get_for_sources(
        self,
        tenant_id: str,
        source_ids: list[UUID],
        limit: int,
    ) -> list[EvidenceSpan]:
        if not source_ids:
            return []

        async with session_factory() as session:
            stmt = (
                select(EvidenceSpanRecord)
                .where(
                    EvidenceSpanRecord.tenant_id == tenant_id,
                    EvidenceSpanRecord.source_id.in_(source_ids),
                )
                .order_by(
                    EvidenceSpanRecord.source_id,
                    EvidenceSpanRecord.start_offset,
                )
                .limit(limit)
            )

            rows = (await session.execute(stmt)).scalars().all()

            return [
                EvidenceSpan(
                    span_id=row.span_id,
                    tenant_id=row.tenant_id,
                    source_id=row.source_id,
                    start_offset=row.start_offset,
                    end_offset=row.end_offset,
                    text=row.text,
                )
                for row in rows
            ]


class PostgresAssertionRepository:
    async def put(self, assertion: CommercialAssertion) -> bool:
        values = assertion.model_dump()

        async with session_factory() as session:
            async with session.begin():
                stmt = insert(
                    AssertionRecord
                ).values(**values).on_conflict_do_nothing(
                    constraint="uq_assertion_tenant_id"
                )

                result = await session.execute(stmt)

                if not result.rowcount:
                    return False

                if assertion.supersedes_assertion_id is not None:
                    await session.execute(
                        AssertionRecord.__table__.update()
                        .where(
                            AssertionRecord.tenant_id == assertion.tenant_id,
                            AssertionRecord.assertion_id
                            == assertion.supersedes_assertion_id,
                        )
                        .values(status="superseded")
                    )

            return True

    async def find(
        self,
        tenant_id: str,
        entity_id: str,
        at_time: datetime | None,
        limit: int,
    ) -> list[CommercialAssertion]:
        async with session_factory() as session:
            stmt = select(AssertionRecord).where(
                AssertionRecord.tenant_id == tenant_id,
                AssertionRecord.entity_id == entity_id,
            )

            if at_time is not None:
                stmt = stmt.where(
                    (
                        AssertionRecord.valid_from.is_(None)
                        | (AssertionRecord.valid_from <= at_time)
                    ),
                    (
                        AssertionRecord.valid_to.is_(None)
                        | (at_time < AssertionRecord.valid_to)
                    ),
                )

            stmt = stmt.order_by(
                AssertionRecord.recorded_at.desc(),
                AssertionRecord.assertion_id.desc(),
            ).limit(limit)

            rows = (await session.execute(stmt)).scalars().all()

            return [
                CommercialAssertion(
                    assertion_id=row.assertion_id,
                    tenant_id=row.tenant_id,
                    entity_id=row.entity_id,
                    attribute=row.attribute,
                    value=row.value,
                    unit=row.unit,
                    scope=row.scope,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    recorded_at=row.recorded_at,
                    status=row.status,
                    confidence=row.confidence,
                    source_id=row.source_id,
                    evidence_span_id=row.evidence_span_id,
                    extractor_name=row.extractor_name,
                    extractor_version=row.extractor_version,
                    supersedes_assertion_id=row.supersedes_assertion_id,
                )
                for row in rows
            ]


class PostgresWorkflowRepository:
    async def get(
        self,
        tenant_id: str,
        case_id: str,
    ) -> WorkflowState | None:
        async with session_factory() as session:
            stmt = select(WorkflowStateRecord).where(
                WorkflowStateRecord.tenant_id == tenant_id,
                WorkflowStateRecord.case_id == case_id,
            )

            row = (await session.execute(stmt)).scalar_one_or_none()

            if row is None:
                return None

            return WorkflowState(
                case_id=row.case_id,
                tenant_id=row.tenant_id,
                stage=row.stage,
                goal=row.goal,
                completed_steps=row.completed_steps,
                pending_steps=row.pending_steps,
                unresolved_conflicts=row.unresolved_conflicts,
                tool_results=row.tool_results,
                approval_state=row.approval_state,
                checkpoint=row.checkpoint,
                retry_count=row.retry_count,
                model_version=row.model_version,
                prompt_version=row.prompt_version,
                updated_at=row.updated_at,
            )

    async def put(self, state: WorkflowState) -> None:
        values = state.model_dump()
        values["updated_at"] = state.updated_at

        async with session_factory() as session:
            stmt = insert(WorkflowStateRecord).values(**values)

            update_values = {
                key: value
                for key, value in values.items()
                if key != "id"
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_workflow_tenant_case",
                set_=update_values,
            )

            await session.execute(stmt)
            await session.commit()


class PostgresRetrievalRepository:
    async def lexical_search(
        self,
        tenant_id: str,
        query: str,
        limit: int,
    ) -> list[RetrievalHit]:
        query = query.strip()

        if not query:
            return []

        if limit < 1:
            raise ValueError("limit must be >= 1")

        statement = text(
            """
            SELECT
                span_id,
                tenant_id,
                source_id,
                text,
                ts_rank_cd(
                    search_vector,
                    websearch_to_tsquery('simple', :query)
                ) AS score
            FROM evidence_span
            WHERE tenant_id = :tenant_id
              AND search_vector @@ websearch_to_tsquery('simple', :query)
            ORDER BY score DESC, span_id
            LIMIT :limit
            """
        )

        async with session_factory() as session:
            result = await session.execute(
                statement,
                {
                    "tenant_id": tenant_id,
                    "query": query,
                    "limit": limit,
                },
            )

            return [
                RetrievalHit(
                    span_id=row.span_id,
                    tenant_id=row.tenant_id,
                    source_id=row.source_id,
                    text=row.text,
                    score=float(row.score),
                )
                for row in result
            ]

    async def put_embedding(
        self,
        embedding: EvidenceEmbedding,
    ) -> bool:
        values = embedding.model_dump()

        async with session_factory() as session:
            stmt = insert(
                EvidenceEmbeddingRecord
            ).values(**values).on_conflict_do_nothing(
                constraint="uq_embedding_tenant_span_model"
            )

            result = await session.execute(stmt)
            await session.commit()

            return bool(result.rowcount)

    async def semantic_search(
        self,
        tenant_id: str,
        query_embedding: list[float],
        model_name: str,
        model_version: str,
        limit: int,
    ) -> list[RetrievalHit]:
        if not query_embedding:
            return []

        if limit < 1:
            raise ValueError("limit must be >= 1")

        distance = EvidenceEmbeddingRecord.embedding.cosine_distance(
            query_embedding
        )

        stmt = (
            select(
                EvidenceEmbeddingRecord.span_id,
                EvidenceEmbeddingRecord.tenant_id,
                EvidenceSpanRecord.source_id,
                EvidenceSpanRecord.text,
                distance.label("distance"),
            )
            .join(
                EvidenceSpanRecord,
                (
                    EvidenceEmbeddingRecord.tenant_id
                    == EvidenceSpanRecord.tenant_id
                )
                & (
                    EvidenceEmbeddingRecord.span_id
                    == EvidenceSpanRecord.span_id
                ),
            )
            .where(
                EvidenceEmbeddingRecord.tenant_id == tenant_id,
                EvidenceEmbeddingRecord.model_name == model_name,
                EvidenceEmbeddingRecord.model_version == model_version,
            )
            .order_by(
                distance,
                EvidenceEmbeddingRecord.span_id,
            )
            .limit(limit)
        )

        async with session_factory() as session:
            rows = (await session.execute(stmt)).all()

            return [
                RetrievalHit(
                    span_id=row.span_id,
                    tenant_id=row.tenant_id,
                    source_id=row.source_id,
                    text=row.text,
                    score=1.0 - float(row.distance),
                )
                for row in rows
            ]