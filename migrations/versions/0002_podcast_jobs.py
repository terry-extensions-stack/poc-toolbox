"""Persist podcast workflows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('podcast_jobs',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.Column('idempotency_key', sa.String(200), nullable=False, unique=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('model_config_id', sa.UUID(), sa.ForeignKey('ai_model_configs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('progress', postgresql.JSONB(), nullable=False),
        sa.Column('output_key', sa.Text()), sa.Column('error', sa.Text()))
    op.create_index('ix_podcast_jobs_status', 'podcast_jobs', ['status'])


def downgrade():
    op.drop_table('podcast_jobs')
