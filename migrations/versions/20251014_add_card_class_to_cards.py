"""Add card_class column to cards table

Revision ID: add_card_class_column
Revises: add_language_to_cards
Create Date: 2025-10-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_card_class_column'
down_revision = 'add_language_to_cards'
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    try:
        cols = [c['name'] for c in inspector.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, 'cards', 'card_class'):
        op.add_column(
            'cards',
            sa.Column('card_class', sa.String(length=50), nullable=True, server_default='General'),
        )

    try:
        op.execute("UPDATE cards SET card_class = 'General' WHERE card_class IS NULL")
    except Exception:
        pass


def downgrade():
    try:
        op.drop_column('cards', 'card_class')
    except Exception:
        pass
