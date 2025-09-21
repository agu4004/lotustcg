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
    # Be idempotent: Only create the table if it doesn't already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'shop_consignment_logs' not in inspector.get_table_names():
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
    # Create indexes if missing; ignore if they already exist
    try:
        op.create_index('ix_consignment_logs_card', 'shop_consignment_logs', ['card_id'])
    except Exception:
        pass
    try:
        op.create_index('ix_consignment_logs_user', 'shop_consignment_logs', ['from_user_id'])
    except Exception:
        pass
    try:
        op.create_index('ix_consignment_logs_created', 'shop_consignment_logs', ['created_at'])
    except Exception:
        pass


def downgrade():
    # Drop indexes/tables only if they exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'shop_consignment_logs' in inspector.get_table_names():
        try:
            op.drop_index('ix_consignment_logs_card')
        except Exception:
            pass
        try:
            op.drop_index('ix_consignment_logs_user')
        except Exception:
            pass
        try:
            op.drop_index('ix_consignment_logs_created')
        except Exception:
            pass
        op.drop_table('shop_consignment_logs')

