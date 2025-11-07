"""add tracking fields to orders (safe version)

Revision ID: 20251107_tracking_safe
Revises:
Create Date: 2025-11-07 22:10:00.000000

This is a safe migration that checks if columns exist before adding them.
Use this if the migration chain is broken.

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251107_tracking_safe'
down_revision = None  # This migration can be applied independently
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    """Check if a column exists in a table"""
    try:
        cols = [c['name'] for c in inspector.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Add tracking_number if missing
    if not _has_column(inspector, 'orders', 'tracking_number'):
        op.add_column('orders', sa.Column('tracking_number', sa.String(120), nullable=True))
        print("✓ Added tracking_number column")
    else:
        print("⊘ tracking_number column already exists")

    # Add tracking_carrier if missing
    if not _has_column(inspector, 'orders', 'tracking_carrier'):
        op.add_column('orders', sa.Column('tracking_carrier', sa.String(80), nullable=True))
        print("✓ Added tracking_carrier column")
    else:
        print("⊘ tracking_carrier column already exists")

    # Add tracking_url if missing
    if not _has_column(inspector, 'orders', 'tracking_url'):
        op.add_column('orders', sa.Column('tracking_url', sa.String(255), nullable=True))
        print("✓ Added tracking_url column")
    else:
        print("⊘ tracking_url column already exists")

    # Add tracking_notes if missing
    if not _has_column(inspector, 'orders', 'tracking_notes'):
        op.add_column('orders', sa.Column('tracking_notes', sa.Text(), nullable=True))
        print("✓ Added tracking_notes column")
    else:
        print("⊘ tracking_notes column already exists")

    # Add shipped_at if missing
    if not _has_column(inspector, 'orders', 'shipped_at'):
        op.add_column('orders', sa.Column('shipped_at', sa.DateTime(), nullable=True))
        print("✓ Added shipped_at column")
    else:
        print("⊘ shipped_at column already exists")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Remove columns if they exist
    if _has_column(inspector, 'orders', 'shipped_at'):
        op.drop_column('orders', 'shipped_at')
    if _has_column(inspector, 'orders', 'tracking_notes'):
        op.drop_column('orders', 'tracking_notes')
    if _has_column(inspector, 'orders', 'tracking_url'):
        op.drop_column('orders', 'tracking_url')
    if _has_column(inspector, 'orders', 'tracking_carrier'):
        op.drop_column('orders', 'tracking_carrier')
    if _has_column(inspector, 'orders', 'tracking_number'):
        op.drop_column('orders', 'tracking_number')
