from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    EvidenceEnvelope,
    EvidenceSpan,
    WorkflowState,
)
from dd_context_engine.storage.db import session_factory
from dd_context_engine.storage.models import (
    AssertionRecord,
    EvidenceSpanRecord,
    SourceRecord,
    WorkflowStateRecord,
)


class PostgresEvidenceRepository:
    async def put_envelope(self, envelope: EvidenceEnvelope) -> bool:
        values = envelope.model_dump()
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
                .order_by(EvidenceSpanRecord.source_id, EvidenceSpanRecord.start_offset)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                EvidenceSpan.model_validate(
                    row.__dict__ | {"span_id": row.span_id}
                )
                for row in rows
            ]


class PostgresAssertionRepository:
    async def put(self, assertion: CommercialAssertion) -> bool:
        values = assertion.model_dump()
        async with session_factory() as session:
            stmt = insert(AssertionRecord).values(**values).on_conflict_do_nothing(
                constraint="uq_assertion_tenant_id"
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount)

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
                    (AssertionRecord.valid_to.is_(None) | (at_time < AssertionRecord.valid_to)),
                )
            stmt = stmt.order_by(AssertionRecord.recorded_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                CommercialAssertion.model_validate(
                    row.__dict__ | {"assertion_id": row.assertion_id}
                )
                for row in rows
            ]


class PostgresWorkflowRepository:
    async def get(self, tenant_id: str, case_id: str) -> WorkflowState | None:
        async with session_factory() as session:
            stmt = select(WorkflowStateRecord).where(
                WorkflowStateRecord.tenant_id == tenant_id,
                WorkflowStateRecord.case_id == case_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return WorkflowState.model_validate(row.__dict__)

    async def put(self, state: WorkflowState) -> None:
        values = state.model_dump()
        values["updated_at"] = state.updated_at
        async with session_factory() as session:
            stmt = insert(WorkflowStateRecord).values(**values)
            update_values = {k: v for k, v in values.items() if k != "id"}
            stmt = stmt.on_conflict_do_update(
                constraint="uq_workflow_tenant_case",
                set_=update_values,
            )
            await session.execute(stmt)
            await session.commit()
