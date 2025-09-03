"""Add is_public field to inventory_items table

Revision ID: add_is_public_field
Revises: user_mgmt_001
Create Date: 2025-09-02 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_public_field'
down_revision = 'user_mgmt_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_public column to inventory_items table
    op.add_column('inventory_items', sa.Column('is_public', sa.Boolean(), nullable=False, default=True))


def downgrade():
    # Remove is_public column from inventory_items table
    op.drop_column('inventory_items', 'is_public')