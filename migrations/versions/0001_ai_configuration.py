"""Create AI model configurations and prompt templates."""

import sqlalchemy as sa

from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    ]


def upgrade() -> None:
    op.create_table(
        'ai_model_configs',
        *audit_columns(),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('base_url', sa.String(2048), nullable=False),
        sa.Column('model_id', sa.String(255), nullable=False),
        sa.Column('api_key_ciphertext', sa.Text(), nullable=False),
    )
    op.create_table(
        'ai_templates',
        *audit_columns(),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('system_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('user_prompt', sa.Text(), nullable=False),
        sa.Column(
            'model_config_id', sa.UUID(), sa.ForeignKey('ai_model_configs.id', ondelete='RESTRICT'), nullable=False
        ),
    )
    op.create_index('ix_ai_templates_model_config_id', 'ai_templates', ['model_config_id'])


def downgrade() -> None:
    op.drop_table('ai_templates')
    op.drop_table('ai_model_configs')
