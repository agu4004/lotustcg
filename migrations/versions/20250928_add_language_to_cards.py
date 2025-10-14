"""Add language field to Card model

Revision ID: add_language_to_cards
Revises: add_card_class_column
Create Date: 2025-09-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_language_to_cards'
down_revision = 'add_card_class_column'
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
