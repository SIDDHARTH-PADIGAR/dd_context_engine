from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceType(StrEnum):
    EMAIL = "email"
    PDF = "pdf"
    SPREADSHEET = "spreadsheet"
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    ERP_RECORD = "erp_record"
    PAYMENT = "payment"
    OTHER = "other"


class AssertionStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONFLICTED = "conflicted"
    HISTORICAL = "historical"


class EvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=128)
    source_type: SourceType
    source_system: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1, max_length=128)
    content_type: str = Field(min_length=1, max_length=256)
    content_uri: str = Field(min_length=1, max_length=2048)
    observed_at: datetime
    ingested_at: datetime
    checksum_sha256: str = Field(min_length=64, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=128)
    source_id: UUID
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> "EvidenceSpan":
        if self.end_offset < self.start_offset:
            raise ValueError("end_offset must be >= start_offset")
        return self


class CommercialAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assertion_id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=128)
    entity_id: str = Field(min_length=1, max_length=256)
    attribute: str = Field(min_length=1, max_length=256)
    value: Any
    unit: str | None = Field(default=None, max_length=64)
    scope: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recorded_at: datetime
    status: AssertionStatus = AssertionStatus.CANDIDATE
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_id: UUID
    evidence_span_id: UUID | None = None
    extractor_name: str = Field(min_length=1, max_length=128)
    extractor_version: str = Field(min_length=1, max_length=128)
    supersedes_assertion_id: UUID | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "CommercialAssertion":
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=256)
    tenant_id: str = Field(min_length=1, max_length=128)
    stage: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=4096)
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    approval_state: str | None = None
    checkpoint: str | None = None
    retry_count: int = Field(default=0, ge=0)
    model_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    updated_at: datetime


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=128)
    case_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=4096)
    entity_id: str | None = Field(default=None, max_length=256)
    at_time: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    max_assertions: int = Field(default=20, ge=1, le=200)
    max_evidence_items: int = Field(default=8, ge=1, le=100)


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    task: str
    workflow_state: WorkflowState | None = None
    assertions: list[CommercialAssertion] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    bounded: bool = True
