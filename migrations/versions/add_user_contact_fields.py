"""
Add user contact and address fields

Revision ID: add_user_contact_fields
Revises: add_order_email
Create Date: 2025-09-05 03:55:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_user_contact_fields'
down_revision = 'add_order_email'
branch_labels = None
depends_on = None


def upgrade():
    cols = [
        ('full_name', sa.String(length=100)),
        ('phone_number', sa.String(length=20)),
        ('address_line', sa.Text()),
        ('address_city', sa.String(length=100)),
        ('address_province', sa.String(length=100)),
        ('address_postal_code', sa.String(length=20)),
        ('address_country', sa.String(length=100)),
    ]
    for name, coltype in cols:
        try:
            op.add_column('users', sa.Column(name, coltype, nullable=True))
        except Exception:
            pass


def downgrade():
    for name in [
        'full_name','phone_number','address_line','address_city','address_province','address_postal_code','address_country']:
        try:
            op.drop_column('users', name)
        except Exception:
            pass

