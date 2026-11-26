"""Persist basic RSS article snapshots."""

import sqlalchemy as sa

from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rss_article_snapshots',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('title', sa.Text()),
        sa.Column('link', sa.Text()),
        sa.Column('cover', sa.Text()),
        sa.Column('publish_at', sa.BigInteger()),
        sa.Column('is_copyright', sa.Boolean()),
        sa.Column('feed_name', sa.Text()),
        sa.Column('feed_cover', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table('rss_article_snapshots')
