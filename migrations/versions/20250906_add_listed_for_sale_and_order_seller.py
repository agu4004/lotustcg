"""Add listed_for_sale to inventory_items; link seller in order_items

Revision ID: add_listed_and_seller_links
Revises: e2098e5db12e
Create Date: 2025-09-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_listed_and_seller_links'
down_revision = 'e2098e5db12e'
branch_labels = None
depends_on = None


def upgrade():
    # inventory_items: add listed_for_sale boolean
    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('listed_for_sale', sa.Boolean(), nullable=False, server_default=sa.false()))
        try:
            batch_op.create_index('ix_inventory_items_market', ['listed_for_sale', 'is_verified', 'quantity'])
        except Exception:
            pass

    # order_items: link to inventory item and seller
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inventory_item_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('seller_user_id', sa.Integer(), nullable=True))
        try:
            batch_op.create_foreign_key('fk_order_items_inventory_item', 'inventory_items', ['inventory_item_id'], ['id'])
        except Exception:
            pass
        try:
            batch_op.create_foreign_key('fk_order_items_seller_user', 'users', ['seller_user_id'], ['id'])
        except Exception:
            pass


def downgrade():
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('fk_order_items_inventory_item', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('fk_order_items_seller_user', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('seller_user_id')
        batch_op.drop_column('inventory_item_id')

    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_inventory_items_market')
        except Exception:
            pass
        batch_op.drop_column('listed_for_sale')

