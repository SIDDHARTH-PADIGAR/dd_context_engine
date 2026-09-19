from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dd_context_engine.domain.schemas import CommercialAssertion, EvidenceSpan


def test_assertion_preserves_version_and_provenance():
    now = datetime.now(timezone.utc)
    assertion = CommercialAssertion(
        tenant_id="tenant-a",
        entity_id="vendor-1",
        attribute="funding_rate",
        value={"value": 0.10},
        valid_from=now,
        recorded_at=now,
        source_id=uuid4(),
        extractor_name="term-extractor",
        extractor_version="v1",
        confidence=0.94,
    )
    assert assertion.extractor_version == "v1"
    assert assertion.source_id


def test_invalid_interval_is_rejected():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        CommercialAssertion(
            tenant_id="tenant-a", entity_id="vendor-1", attribute="x", value=1,
            valid_from=now, valid_to=now - timedelta(seconds=1), recorded_at=now,
            source_id=uuid4(), extractor_name="x", extractor_version="v1",
        )


def test_evidence_span_must_not_reverse_offsets():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            tenant_id="tenant-a", source_id=uuid4(), start_offset=12, end_offset=5, text="bad"
        )
