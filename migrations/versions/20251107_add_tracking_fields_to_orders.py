"""add tracking fields to orders

Revision ID: 20251107_tracking
Revises: add_card_class_column
Create Date: 2025-11-07 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251107_tracking'
down_revision = 'add_card_class_column'
branch_labels = None
depends_on = None


def upgrade():
    # Add tracking-related columns to orders table
    op.add_column('orders', sa.Column('tracking_number', sa.String(120), nullable=True))
    op.add_column('orders', sa.Column('tracking_carrier', sa.String(80), nullable=True))
    op.add_column('orders', sa.Column('tracking_url', sa.String(255), nullable=True))
    op.add_column('orders', sa.Column('tracking_notes', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('shipped_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remove tracking-related columns from orders table
    op.drop_column('orders', 'shipped_at')
    op.drop_column('orders', 'tracking_notes')
    op.drop_column('orders', 'tracking_url')
    op.drop_column('orders', 'tracking_carrier')
    op.drop_column('orders', 'tracking_number')
