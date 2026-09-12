"""Drop camera_role and camera.role; engine-level algorithms

Revision ID: 006
Revises: 005
Create Date: 2026-09-12 10:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.drop_column('camera_role')

    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.drop_column('role')


def downgrade():
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=30), nullable=True))

    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('camera_role', sa.String(length=30), nullable=True))
