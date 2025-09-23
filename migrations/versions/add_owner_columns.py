"""Add owner columns to cards and shop_inventory_items

Revision ID: add_owner_columns
Revises: create_shop_consignment_logs
Create Date: 2025-09-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_owner_columns'
down_revision = 'create_shop_consignment_logs'
branch_labels = None
depends_on = None


def upgrade():
    # Add owner column to cards (default 'shop')
    try:
        op.add_column('cards', sa.Column('owner', sa.String(length=80), nullable=True, server_default='shop'))
    except Exception:
        pass
    # Backfill existing rows to 'shop' where null
    try:
        op.execute("UPDATE cards SET owner = 'shop' WHERE owner IS NULL")
    except Exception:
        pass

    # Add owner column to shop_inventory_items
    try:
        op.add_column('shop_inventory_items', sa.Column('owner', sa.String(length=80), nullable=True))
    except Exception:
        pass
    # Backfill from users.username where possible
    try:
        op.execute(
            """
            UPDATE shop_inventory_items AS s
            SET owner = (
                SELECT u.username FROM users u WHERE u.id = s.from_user_id
            )
            WHERE owner IS NULL
            """
        )
    except Exception:
        pass


def downgrade():
    # Drop added columns
    try:
        op.drop_column('shop_inventory_items', 'owner')
    except Exception:
        pass
    try:
        op.drop_column('cards', 'owner')
    except Exception:
        pass

