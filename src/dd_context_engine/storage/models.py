from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceRecord(Base):
    __tablename__ = "source_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_source_tenant_id",
        ),
        UniqueConstraint(
            "source_id",
            name="uq_source_id",
        ),
        Index(
            "ix_source_record_tenant_id",
            "tenant_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    source_version: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    content_uri: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )


class EvidenceSpanRecord(Base):
    __tablename__ = "evidence_span"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "span_id",
            name="uq_span_tenant_id",
        ),
        Index(
            "ix_evidence_span_tenant_id",
            "tenant_id",
        ),
        Index(
            "ix_evidence_span_source_id",
            "source_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    span_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_record.source_id"),
        nullable=False,
    )
    start_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    end_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class AssertionRecord(Base):
    __tablename__ = "commercial_assertion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "assertion_id",
            name="uq_assertion_tenant_id",
        ),
        Index(
            "ix_assertion_tenant_id",
            "tenant_id",
        ),
        Index(
            "ix_assertion_entity_id",
            "entity_id",
        ),
        Index(
            "ix_assertion_entity_attribute",
            "entity_id",
            "attribute",
        ),
        Index(
            "ix_assertion_recorded_at",
            "recorded_at",
        ),
        Index(
            "ix_assertion_valid_from",
            "valid_from",
        ),
        Index(
            "ix_assertion_valid_to",
            "valid_to",
        ),
        Index(
            "ix_assertion_status",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    assertion_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    entity_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    attribute: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    value: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
    )
    unit: Mapped[str | None] = mapped_column(
        String(64),
    )
    scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    confidence: Mapped[float | None]
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    evidence_span_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )
    extractor_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    extractor_version: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    supersedes_assertion_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )


class WorkflowStateRecord(Base):
    __tablename__ = "workflow_state"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "case_id",
            name="uq_workflow_tenant_case",
        ),
        Index(
            "ix_workflow_tenant_id",
            "tenant_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    goal: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    completed_steps: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    pending_steps: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    unresolved_conflicts: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    tool_results: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    approval_state: Mapped[str | None] = mapped_column(
        String(64),
    )
    checkpoint: Mapped[str | None] = mapped_column(
        Text,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    model_version: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_event"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "event_key",
            name="uq_outbox_tenant_event",
        ),
        Index(
            "ix_outbox_tenant_id",
            "tenant_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    event_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class EvidenceEmbeddingRecord(Base):
    __tablename__ = "evidence_embedding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "span_id",
            "model_name",
            "model_version",
            name="uq_embedding_tenant_span_model",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "span_id"],
            ["evidence_span.tenant_id", "evidence_span.span_id"],
            name="fk_embedding_span_tenant",
        ),
        Index(
            "ix_embedding_tenant_model",
            "tenant_id",
            "model_name",
            "model_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    embedding_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    span_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(),
        nullable=False,
    )