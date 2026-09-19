from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(128), nullable=False),
        sa.Column("source_version", sa.String(128), nullable=False),
        sa.Column("content_type", sa.String(256), nullable=False),
        sa.Column("content_uri", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("permissions", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_source_tenant_id"),
        sa.UniqueConstraint("source_id", name="uq_source_id"),
    )
    op.create_index("ix_source_record_tenant_id", "source_record", ["tenant_id"])

    op.create_table(
        "evidence_span",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source_record.source_id"]),
        sa.UniqueConstraint("tenant_id", "span_id", name="uq_span_tenant_id"),
    )
    op.create_index("ix_evidence_span_tenant_id", "evidence_span", ["tenant_id"])
    op.create_index("ix_evidence_span_source_id", "evidence_span", ["source_id"])

    op.create_table(
        "commercial_assertion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assertion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("entity_id", sa.String(256), nullable=False),
        sa.Column("attribute", sa.String(256), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.String(64)),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_span_id", postgresql.UUID(as_uuid=True)),
        sa.Column("extractor_name", sa.String(128), nullable=False),
        sa.Column("extractor_version", sa.String(128), nullable=False),
        sa.Column("supersedes_assertion_id", postgresql.UUID(as_uuid=True)),
        sa.UniqueConstraint("tenant_id", "assertion_id", name="uq_assertion_tenant_id"),
    )
    op.create_index("ix_assertion_tenant_id", "commercial_assertion", ["tenant_id"])
    op.create_index("ix_assertion_entity_id", "commercial_assertion", ["entity_id"])
    op.create_index("ix_assertion_entity_attribute", "commercial_assertion", ["entity_id", "attribute"])
    op.create_index("ix_assertion_recorded_at", "commercial_assertion", ["recorded_at"])
    op.create_index("ix_assertion_valid_from", "commercial_assertion", ["valid_from"])
    op.create_index("ix_assertion_valid_to", "commercial_assertion", ["valid_to"])
    op.create_index("ix_assertion_status", "commercial_assertion", ["status"])

    op.create_table(
        "workflow_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(256), nullable=False),
        sa.Column("stage", sa.String(128), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("completed_steps", postgresql.JSONB(), nullable=False),
        sa.Column("pending_steps", postgresql.JSONB(), nullable=False),
        sa.Column("unresolved_conflicts", postgresql.JSONB(), nullable=False),
        sa.Column("tool_results", postgresql.JSONB(), nullable=False),
        sa.Column("approval_state", sa.String(64)),
        sa.Column("checkpoint", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "case_id", name="uq_workflow_tenant_case"),
    )
    op.create_index("ix_workflow_tenant_id", "workflow_state", ["tenant_id"])

    op.create_table(
        "outbox_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("event_key", sa.String(512), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_key", name="uq_outbox_tenant_event"),
    )
    op.create_index("ix_outbox_tenant_id", "outbox_event", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_tenant_id", table_name="outbox_event")
    op.drop_table("outbox_event")
    op.drop_index("ix_workflow_tenant_id", table_name="workflow_state")
    op.drop_table("workflow_state")
    for idx in [
        "ix_assertion_status", "ix_assertion_valid_to", "ix_assertion_valid_from",
        "ix_assertion_recorded_at", "ix_assertion_entity_attribute", "ix_assertion_entity_id",
        "ix_assertion_tenant_id",
    ]:
        op.drop_index(idx, table_name="commercial_assertion")
    op.drop_table("commercial_assertion")
    op.drop_index("ix_evidence_span_source_id", table_name="evidence_span")
    op.drop_index("ix_evidence_span_tenant_id", table_name="evidence_span")
    op.drop_table("evidence_span")
    op.drop_index("ix_source_record_tenant_id", table_name="source_record")
    op.drop_table("source_record")
