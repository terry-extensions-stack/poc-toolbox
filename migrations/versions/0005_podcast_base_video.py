"""Separate clean base videos from the current edited video."""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('podcast_jobs', sa.Column('base_video_key', sa.Text()))
    op.add_column('podcast_jobs', sa.Column('media_metadata', postgresql.JSONB()))
    op.add_column('podcast_jobs', sa.Column('workflow_version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('podcast_jobs', sa.Column('current_render_id', sa.UUID()))
    op.add_column('podcast_jobs', sa.Column('active_render_id', sa.UUID()))


def downgrade():
    for column in ('active_render_id', 'current_render_id', 'workflow_version', 'media_metadata', 'base_video_key'):
        op.drop_column('podcast_jobs', column)
