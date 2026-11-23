"""Allow podcast jobs to use environment-configured models."""

from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('podcast_jobs', 'model_config_id', nullable=True)


def downgrade():
    op.alter_column('podcast_jobs', 'model_config_id', nullable=False)
