from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from dd_context_engine.domain.schemas import AssertionStatus, CommercialAssertion
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import AssertionRecord
from dd_context_engine.storage.postgres import PostgresAssertionRepository


@pytest.mark.asyncio
async def test_assertion_supersession_is_transactional_and_historical():
    tenant_id = f"assertion-integration-{uuid4()}"
    other_tenant_id = f"other-tenant-{uuid4()}"
    source_a = uuid4()
    source_b = uuid4()
    assertion_a_id = uuid4()
    assertion_b_id = uuid4()
    now = datetime.now(UTC)

    repository = PostgresAssertionRepository()

    assertion_a = CommercialAssertion(
        assertion_id=assertion_a_id,
        tenant_id=tenant_id,
        entity_id="vendor-1",
        attribute="funding_rate",
        value=0.10,
        recorded_at=now,
        status=AssertionStatus.ACTIVE,
        source_id=source_a,
        extractor_name="integration-test",
        extractor_version="1",
    )

    assertion_b = CommercialAssertion(
        assertion_id=assertion_b_id,
        tenant_id=tenant_id,
        entity_id="vendor-1",
        attribute="funding_rate",
        value=0.12,
        recorded_at=now + timedelta(minutes=1),
        status=AssertionStatus.ACTIVE,
        source_id=source_b,
        supersedes_assertion_id=assertion_a_id,
        extractor_name="integration-test",
        extractor_version="1",
    )

    other_assertion = CommercialAssertion(
        assertion_id=uuid4(),
        tenant_id=other_tenant_id,
        entity_id="vendor-1",
        attribute="funding_rate",
        value=0.99,
        recorded_at=now,
        status=AssertionStatus.ACTIVE,
        source_id=uuid4(),
        extractor_name="integration-test",
        extractor_version="1",
    )

    try:
        assert await repository.put(assertion_a) is True
        assert await repository.put(other_assertion) is True
        assert await repository.put(assertion_b) is True

        async with session_factory() as session:
            stored_a = (
                await session.execute(
                    select(AssertionRecord).where(
                        AssertionRecord.tenant_id == tenant_id,
                        AssertionRecord.assertion_id == assertion_a_id,
                    )
                )
            ).scalar_one()

            stored_b = (
                await session.execute(
                    select(AssertionRecord).where(
                        AssertionRecord.tenant_id == tenant_id,
                        AssertionRecord.assertion_id == assertion_b_id,
                    )
                )
            ).scalar_one()

        assert stored_a is not None
        assert stored_b is not None
        assert stored_a.status == AssertionStatus.SUPERSEDED.value
        assert stored_b.status == AssertionStatus.ACTIVE.value
        assert stored_a.value == 0.10
        assert stored_b.value == 0.12
        assert stored_a.valid_to == assertion_b.valid_from

        tenant_assertions = await repository.find(
            tenant_id=tenant_id,
            entity_id="vendor-1",
            at_time=None,
            limit=10,
        )

        assert {item.assertion_id for item in tenant_assertions} == {
            assertion_a_id,
            assertion_b_id,
        }

        other_assertions = await repository.find(
            tenant_id=other_tenant_id,
            entity_id="vendor-1",
            at_time=None,
            limit=10,
        )

        assert len(other_assertions) == 1
        assert other_assertions[0].value == 0.99

    finally:
        async with session_factory() as session:
            await session.execute(
                delete(AssertionRecord).where(
                    AssertionRecord.tenant_id.in_(
                        [tenant_id, other_tenant_id]
                    )
                )
            )
            await session.commit()
            await engine.dispose()