"""
Add Store Credit support: currency_code, unique CREDIT index, quantity >= 0 check, credit_ledger, idempotency_keys.

Revision ID: 0001_credit
Revises: 
Create Date: 2025-09-05 02:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision = '0001_credit'
down_revision = '210a2ab185a6'
branch_labels = None
depends_on = None


def _has_column(bind, table_name, column_name):
    insp = reflection.Inspector.from_engine(bind)
    cols = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in cols


def _table_exists(bind, table_name: str) -> bool:
    try:
        return table_name in sa.inspect(bind).get_table_names()
    except Exception:
        return False


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    try:
        idxs = sa.inspect(bind).get_indexes(table_name)
        return any(ix.get('name') == index_name for ix in idxs)
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1) cards: add currency_code if missing
    if not _has_column(bind, 'cards', 'currency_code'):
        op.add_column('cards', sa.Column('currency_code', sa.String(length=10), nullable=False, server_default='VND'))

    # 2) inventory_items: add non-negative quantity check (skip if SQLite)
    if dialect != 'sqlite':
        try:
            op.create_check_constraint('chk_qty_nonneg', 'inventory_items', 'quantity >= 0')
        except Exception:
            pass

    # 3) CREDIT unique index on cards (partial index on set_name='CREDIT')
    if dialect == 'postgresql':
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_card_denom
            ON cards (set_name, price, foiling, rarity, art_style)
            WHERE set_name = 'CREDIT';
        """)
    else:
        # SQLite supports partial indexes; attempt creation
        try:
            op.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_card_denom
                ON cards (set_name, price, foiling, rarity, art_style)
                WHERE set_name = 'CREDIT';
            """)
        except Exception:
            # Fallback: no-op
            pass

    # 4) credit_ledger table (idempotent)
    if not _table_exists(bind, 'credit_ledger'):
        op.create_table(
            'credit_ledger',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('entry_ts', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('amount_vnd', sa.BigInteger(), nullable=False),
            sa.Column('direction', sa.String(length=10), nullable=False),
            sa.Column('kind', sa.String(length=20), nullable=False),
            sa.Column('related_order_id', sa.Integer(), nullable=True),
            sa.Column('related_inventory_item_id', sa.Integer(), nullable=True),
            sa.Column('admin_id', sa.Integer(), nullable=True),
            sa.Column('idempotency_key', sa.String(length=255), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.CheckConstraint('amount_vnd > 0', name='chk_credit_amount_positive'),
            sa.CheckConstraint("direction in ('debit','credit')", name='chk_credit_direction'),
            sa.CheckConstraint("kind in ('issue','redeem','transfer_in','transfer_out','revoke','adjust')", name='chk_credit_kind'),
        )
    if not _index_exists(bind, 'credit_ledger', 'ix_credit_ledger_user_ts'):
        try:
            op.create_index('ix_credit_ledger_user_ts', 'credit_ledger', ['user_id', 'entry_ts'], unique=False)
        except Exception:
            pass

    if dialect == 'postgresql':
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_ledger_idem
            ON credit_ledger (idempotency_key)
            WHERE idempotency_key IS NOT NULL;
        """)

    # 5) idempotency_keys table (idempotent)
    if not _table_exists(bind, 'idempotency_keys'):
        op.create_table(
            'idempotency_keys',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('key', sa.String(length=255), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('last_seen_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column('scope', sa.String(length=100), nullable=True),
            sa.Column('request_fingerprint', sa.String(length=255), nullable=True),
        )
    # Only create a separate unique index if one on (key) doesn't already exist
    try:
        idxs = sa.inspect(bind).get_indexes('idempotency_keys')
        has_unique_key_idx = any(ix.get('unique') and ix.get('column_names') == ['key'] for ix in idxs)
    except Exception:
        has_unique_key_idx = False
    if not has_unique_key_idx and not _index_exists(bind, 'idempotency_keys', 'ix_idempotency_keys_key'):
        try:
            op.create_index('ix_idempotency_keys_key', 'idempotency_keys', ['key'], unique=True)
        except Exception:
            pass


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Drop idempotency table (guarded)
    if _table_exists(bind, 'idempotency_keys'):
        try:
            if _index_exists(bind, 'idempotency_keys', 'ix_idempotency_keys_key'):
                op.drop_index('ix_idempotency_keys_key', table_name='idempotency_keys')
        except Exception:
            pass
        op.drop_table('idempotency_keys')

    # Drop ledger (guarded)
    if dialect == 'postgresql':
        op.execute("DROP INDEX IF EXISTS ux_credit_ledger_idem;")
    if _table_exists(bind, 'credit_ledger'):
        try:
            if _index_exists(bind, 'credit_ledger', 'ix_credit_ledger_user_ts'):
                op.drop_index('ix_credit_ledger_user_ts', table_name='credit_ledger')
        except Exception:
            pass
        op.drop_table('credit_ledger')

    # Drop credit unique index
    try:
        op.execute("DROP INDEX IF EXISTS ux_credit_card_denom;")
    except Exception:
        pass

    # Drop inventory check constraint when supported
    if dialect != 'sqlite':
        try:
            op.drop_constraint('chk_qty_nonneg', 'inventory_items', type_='check')
        except Exception:
            pass

    # Drop currency_code column (safe)
    try:
        op.drop_column('cards', 'currency_code')
    except Exception:
        pass
