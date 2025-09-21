"""
Add user_id foreign key to orders to link orders to users

Revision ID: add_order_user_id
Revises: add_order_number_to_orders
Create Date: 2025-09-05 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_order_user_id'
down_revision = 'add_order_number_to_orders'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('orders', sa.Column('user_id', sa.Integer(), nullable=True))
        op.create_index('ix_orders_user_id', 'orders', ['user_id'], unique=False)
        # Note: SQLite can't easily add FK constraints after table creation. We keep it nullable and indexed.
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index('ix_orders_user_id', table_name='orders')
    except Exception:
        pass
    try:
        op.drop_column('orders', 'user_id')
    except Exception:
        pass

