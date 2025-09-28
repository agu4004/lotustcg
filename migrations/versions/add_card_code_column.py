"""Add card_code column to cards table

Revision ID: add_card_code_column
Revises: add_owner_columns
Create Date: 2025-09-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_card_code_column'
down_revision = 'add_owner_columns'
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

    # Add card_code if missing
    if not _has_column(inspector, 'cards', 'card_code'):
        op.add_column('cards', sa.Column('card_code', sa.String(length=80), nullable=True))

    # Best-effort non-unique index for faster lookups (ignore if not supported)
    try:
        op.create_index('ix_cards_card_code', 'cards', ['card_code'], unique=False)
    except Exception:
        pass


def downgrade():
    # Drop index then column (ignore errors if they don't exist)
    try:
        op.drop_index('ix_cards_card_code', table_name='cards')
    except Exception:
        pass
    try:
        op.drop_column('cards', 'card_code')
    except Exception:
        pass

