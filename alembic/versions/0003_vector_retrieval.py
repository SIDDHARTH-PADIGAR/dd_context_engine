from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR


revision = "0003_vector_retrieval"
down_revision = "0002_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "evidence_embedding",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
        ),
        sa.Column(
            "embedding_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "span_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "model_name",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "model_version",
            sa.String(128),
            nullable=False,
        ),
        sa.Column(
            "dimensions",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            VECTOR(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "span_id"],
            ["evidence_span.tenant_id", "evidence_span.span_id"],
            name="fk_embedding_span_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "span_id",
            "model_name",
            "model_version",
            name="uq_embedding_tenant_span_model",
        ),
    )

    op.create_index(
        "ix_embedding_tenant_model",
        "evidence_embedding",
        ["tenant_id", "model_name", "model_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_embedding_tenant_model",
        table_name="evidence_embedding",
    )
    op.drop_table("evidence_embedding")