"""Fontes de vídeo e legendas para filmes e episódios."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("movie", "episode"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("video_url", sa.String(2048), nullable=True))
            batch.add_column(sa.Column("video_type", sa.String(12), nullable=False, server_default="auto"))
            batch.add_column(sa.Column("subtitle_url", sa.String(2048), nullable=True))


def downgrade():
    for table in ("episode", "movie"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("subtitle_url")
            batch.drop_column("video_type")
            batch.drop_column("video_url")
