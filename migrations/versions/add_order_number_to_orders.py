"""
Add order_number field to orders table for display

Revision ID: add_order_number_to_orders
Revises: add_user_contact_fields
Create Date: 2025-09-05 21:35:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_order_number_to_orders'
down_revision = 'add_user_contact_fields'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('orders', sa.Column('order_number', sa.String(length=30), nullable=True))
    except Exception:
        pass
    try:
        op.create_index('ix_orders_order_number', 'orders', ['order_number'], unique=False)
    except Exception:
        pass
    try:
        op.execute('UPDATE orders SET order_number = id WHERE order_number IS NULL')
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index('ix_orders_order_number', table_name='orders')
    except Exception:
        pass
    try:
        op.drop_column('orders', 'order_number')
    except Exception:
        pass

