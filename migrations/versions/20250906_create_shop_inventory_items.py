"""Create shop_inventory_items table for consignment tracking

Revision ID: create_shop_inventory_items
Revises: add_listed_and_seller_links
Create Date: 2025-09-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'create_shop_inventory_items'
down_revision = 'add_listed_and_seller_links'
branch_labels = None
depends_on = None


def upgrade():
    # Be idempotent: Only create the table if it doesn't already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'shop_inventory_items' not in inspector.get_table_names():
        op.create_table(
            'shop_inventory_items',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('card_id', sa.Integer(), sa.ForeignKey('cards.id'), nullable=False, index=True),
            sa.Column('from_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
            sa.Column('source_inventory_item_id', sa.Integer(), sa.ForeignKey('inventory_items.id'), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
    # Create indexes if missing; ignore if they already exist
    try:
        op.create_index('ix_shop_items_card', 'shop_inventory_items', ['card_id'])
    except Exception:
        pass
    try:
        op.create_index('ix_shop_items_from_user', 'shop_inventory_items', ['from_user_id'])
    except Exception:
        pass


def downgrade():
    # Drop indexes/tables only if they exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'shop_inventory_items' in inspector.get_table_names():
        try:
            op.drop_index('ix_shop_items_card')
        except Exception:
            pass
        try:
            op.drop_index('ix_shop_items_from_user')
        except Exception:
            pass
        op.drop_table('shop_inventory_items')

