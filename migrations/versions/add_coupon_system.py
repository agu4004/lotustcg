"""Add coupon system with Coupon model and order coupon fields

Revision ID: add_coupon_system
Revises: add_is_public_field
Create Date: 2025-09-03 07:02:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_coupon_system'
down_revision = 'add_is_public_field'
branch_labels = None
depends_on = None


def upgrade():
    # Create coupons table
    op.create_table('coupons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('discount_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('valid_from', sa.DateTime(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # Add coupon fields to orders table
    op.add_column('orders', sa.Column('coupon_id', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('coupon_code', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=False))
    op.add_column('orders', sa.Column('discounted_total', sa.Numeric(precision=10, scale=2), nullable=True))

    # Create foreign key constraint
    op.create_foreign_key('fk_orders_coupon_id', 'orders', 'coupons', ['coupon_id'], ['id'])

    # Create index on coupon code for faster lookups
    op.create_index('ix_coupons_code', 'coupons', ['code'])


def downgrade():
    # Remove foreign key constraint
    op.drop_constraint('fk_orders_coupon_id', 'orders', type_='foreignkey')

    # Remove added columns from orders table
    op.drop_column('orders', 'discounted_total')
    op.drop_column('orders', 'discount_amount')
    op.drop_column('orders', 'coupon_code')
    op.drop_column('orders', 'coupon_id')

    # Drop index
    op.drop_index('ix_coupons_code', table_name='coupons')

    # Drop coupons table
    op.drop_table('coupons')