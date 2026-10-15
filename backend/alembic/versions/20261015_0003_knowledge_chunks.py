"""创建 RAG 父子片段表。

Revision ID: 20261015_0003
Revises: 20261014_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261015_0003"
down_revision: str | None = "20261014_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chunk_id", sa.String(length=300), nullable=False, unique=True),
        sa.Column("document_id", sa.String(length=120), nullable=False),
        sa.Column("parent_chunk_id", sa.String(length=300), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title_path", sa.JSON(), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("source_anchor", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_text", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("vector_indexed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.document_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_chunk_id"], ["knowledge_chunks.chunk_id"], ondelete="CASCADE"
        ),
    )
    for column in (
        "chunk_id",
        "document_id",
        "parent_chunk_id",
        "level",
        "content_hash",
        "vector_indexed",
    ):
        op.create_index(f"ix_knowledge_chunks_{column}", "knowledge_chunks", [column])


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
