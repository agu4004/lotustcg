"""
Add email field to orders table

Revision ID: add_order_email
Revises: 0001_credit
Create Date: 2025-09-05 03:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_order_email'
down_revision = '0001_credit'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('orders', sa.Column('email', sa.String(length=120), nullable=True))
    except Exception:
        # For sqlite or if column already exists
        pass


def downgrade():
    try:
        op.drop_column('orders', 'email')
    except Exception:
        pass

