"""Exam algorithms/tasks refactor: engine, camera role, alert task link

Revision ID: 005
Revises: 004
Create Date: 2026-09-12 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('engine', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('camera_role', sa.String(length=30), nullable=True))

    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=30), nullable=True))

    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('algorithm_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_alerts_task_id', 'tasks', ['task_id'], ['id'])
        batch_op.create_foreign_key('fk_alerts_algorithm_id', 'algorithms', ['algorithm_id'], ['id'])

    # 旧数据：engine 缺省等于 type
    op.execute("UPDATE algorithms SET engine = type WHERE engine IS NULL OR engine = ''")
    op.execute("UPDATE cameras SET role = 'any' WHERE role IS NULL OR role = ''")


def downgrade():
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_alerts_algorithm_id', type_='foreignkey')
        batch_op.drop_constraint('fk_alerts_task_id', type_='foreignkey')
        batch_op.drop_column('algorithm_id')
        batch_op.drop_column('task_id')

    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.drop_column('role')

    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.drop_column('camera_role')
        batch_op.drop_column('category')
        batch_op.drop_column('engine')
