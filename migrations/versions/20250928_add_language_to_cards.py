"""Add language field to Card model

Revision ID: add_language_to_cards
Revises: 0fdc9548ed30
Create Date: 2025-09-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_language_to_cards'
down_revision = '0fdc9548ed30'
branch_labels = None
depends_on = None


def upgrade():
    # Add language column to cards; default to 'English'
    try:
        with op.batch_alter_table('cards', schema=None) as batch_op:
            batch_op.add_column(sa.Column('language', sa.String(length=20), nullable=True, server_default='English'))
    except Exception:
        # Be tolerant if column exists or DB backend differs
        pass


def downgrade():
    try:
        with op.batch_alter_table('cards', schema=None) as batch_op:
            batch_op.drop_column('language')
    except Exception:
        pass

