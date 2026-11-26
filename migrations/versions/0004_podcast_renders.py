"""Keep independent composition versions of completed podcasts."""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'podcast_renders',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.Column('source_job_id', sa.UUID(), sa.ForeignKey('podcast_jobs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('idempotency_key', sa.String(200), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('progress', postgresql.JSONB(), nullable=False),
        sa.Column('output_key', sa.Text()),
        sa.Column('error', sa.Text()),
        sa.UniqueConstraint('source_job_id', 'idempotency_key', name='uq_podcast_render_submission'),
    )
    op.create_index('ix_podcast_renders_source_job_id', 'podcast_renders', ['source_job_id'])
    op.create_index('ix_podcast_renders_status', 'podcast_renders', ['status'])


def downgrade():
    op.drop_table('podcast_renders')
