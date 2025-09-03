"""Add missing user management fields to users table

Revision ID: 210a2ab185a6
Revises: add_coupon_system
Create Date: 2025-09-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '210a2ab185a6'
down_revision = 'add_coupon_system'
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

    # last_login
    if not _has_column(inspector, 'users', 'last_login'):
        op.add_column('users', sa.Column('last_login', sa.DateTime(), nullable=True))

    # account_status
    if not _has_column(inspector, 'users', 'account_status'):
        op.add_column(
            'users',
            sa.Column('account_status', sa.String(length=20), nullable=False, server_default='active'),
        )

    # suspension_reason
    if not _has_column(inspector, 'users', 'suspension_reason'):
        op.add_column('users', sa.Column('suspension_reason', sa.Text(), nullable=True))

    # suspension_expires
    if not _has_column(inspector, 'users', 'suspension_expires'):
        op.add_column('users', sa.Column('suspension_expires', sa.DateTime(), nullable=True))

    # password reset fields
    if not _has_column(inspector, 'users', 'password_reset_token'):
        op.add_column('users', sa.Column('password_reset_token', sa.String(length=256), nullable=True))

    if not _has_column(inspector, 'users', 'password_reset_expires'):
        op.add_column('users', sa.Column('password_reset_expires', sa.DateTime(), nullable=True))

    # two-factor fields
    if not _has_column(inspector, 'users', 'two_factor_enabled'):
        op.add_column(
            'users',
            sa.Column('two_factor_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        )

    if not _has_column(inspector, 'users', 'two_factor_secret'):
        op.add_column('users', sa.Column('two_factor_secret', sa.String(length=256), nullable=True))

    # Optional: add helpful indexes if they don't exist (idempotent via raw SQL)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_last_login ON users (last_login)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_account_status ON users (account_status)")


def downgrade():
    # Drop indexes first (idempotent)
    op.execute("DROP INDEX IF EXISTS idx_users_account_status")
    op.execute("DROP INDEX IF EXISTS idx_users_last_login")

    # Drop columns if they exist (use raw SQL for IF EXISTS to be safe across drift)
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS two_factor_secret")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS two_factor_enabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_expires")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_token")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS suspension_expires")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS suspension_reason")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS account_status")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login")

