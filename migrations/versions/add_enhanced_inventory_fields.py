"""Add enhanced fields to inventory_items table

Revision ID: add_enhanced_inventory_fields
Revises: f1234567890
Create Date: 2025-08-30 19:52:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_enhanced_inventory_fields'
down_revision = 'f1234567890'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to inventory_items table
    op.add_column('inventory_items', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('inventory_items', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('inventory_items', sa.Column('grade', sa.String(length=20), nullable=True))
    op.add_column('inventory_items', sa.Column('language', sa.String(length=20), nullable=True))
    op.add_column('inventory_items', sa.Column('foil_type', sa.String(length=50), nullable=True))
    op.add_column('inventory_items', sa.Column('is_mint', sa.Boolean(), nullable=True))


def downgrade():
    # Remove the added columns
    op.drop_column('inventory_items', 'is_mint')
    op.drop_column('inventory_items', 'foil_type')
    op.drop_column('inventory_items', 'language')
    op.drop_column('inventory_items', 'grade')
    op.drop_column('inventory_items', 'notes')
    op.drop_column('inventory_items', 'updated_at')