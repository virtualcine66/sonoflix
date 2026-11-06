"""Fontes criptografadas, revisão TMDB e diagnóstico de reprodução."""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("media_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("encrypted_url", sa.Text(), nullable=False),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("group_name", sa.String(255), nullable=False),
        sa.Column("search_title", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("year", sa.Integer()),
        sa.Column("season_number", sa.Integer()),
        sa.Column("episode_number", sa.Integer()),
        sa.Column("match_status", sa.String(20), nullable=False),
        sa.Column("candidates", sa.JSON()),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movie.id", ondelete="SET NULL")),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="SET NULL")),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_code", sa.String(40)),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("movie_id IS NULL OR episode_id IS NULL", name="one_source_target"))
    for col in ("movie_id", "episode_id", "match_status"):
        op.create_index("ix_media_source_" + col, "media_source", [col])


def downgrade():
    op.drop_table("media_source")
