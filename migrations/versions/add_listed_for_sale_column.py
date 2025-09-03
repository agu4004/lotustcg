"""Add listed_for_sale column to inventory_items table

Revision ID: add_listed_for_sale_column
Revises: add_enhanced_inventory_fields
Create Date: 2025-08-30 20:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_listed_for_sale_column'
down_revision = 'add_enhanced_inventory_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Add listed_for_sale column to inventory_items table
    op.add_column('inventory_items', sa.Column('listed_for_sale', sa.Boolean(), nullable=True, default=False))


def downgrade():
    # Remove the listed_for_sale column
    op.drop_column('inventory_items', 'listed_for_sale')