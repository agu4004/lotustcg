"""Create shop consignment logs table

Revision ID: create_shop_consignment_logs
Revises: create_shop_inventory_items
Create Date: 2025-09-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'create_shop_consignment_logs'
down_revision = 'create_shop_inventory_items'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shop_consignment_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('card_id', sa.Integer(), sa.ForeignKey('cards.id'), nullable=False),
        sa.Column('from_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_inventory_item_id', sa.Integer(), sa.ForeignKey('inventory_items.id'), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    try:
        op.create_index('ix_consignment_logs_card', 'shop_consignment_logs', ['card_id'])
        op.create_index('ix_consignment_logs_user', 'shop_consignment_logs', ['from_user_id'])
        op.create_index('ix_consignment_logs_created', 'shop_consignment_logs', ['created_at'])
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index('ix_consignment_logs_card')
        op.drop_index('ix_consignment_logs_user')
        op.drop_index('ix_consignment_logs_created')
    except Exception:
        pass
    op.drop_table('shop_consignment_logs')

