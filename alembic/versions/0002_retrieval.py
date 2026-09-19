from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_retrieval"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_span",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', text)",
                persisted=True,
            ),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_evidence_span_search_vector",
        "evidence_span",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_span_search_vector",
        table_name="evidence_span",
    )
    op.drop_column("evidence_span", "search_vector")