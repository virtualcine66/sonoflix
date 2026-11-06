"""Identidade do catálogo local independente da identificação TMDB."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    for table in ('movie', 'series'):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('catalog_key', sa.String(64), nullable=True))
            batch.create_unique_constraint(f'uq_{table}_catalog_key', ['catalog_key'])


def downgrade():
    for table in ('movie', 'series'):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'uq_{table}_catalog_key', type_='unique')
            batch.drop_column('catalog_key')
