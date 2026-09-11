"""Add message column to alerts

Revision ID: 004
Revises: 003
Create Date: 2026-09-11 21:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('message', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_column('message')
