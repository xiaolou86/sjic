"""Task may bind one object-detection algorithm and one pose algorithm

Revision ID: 011_task_exam_pipeline
Revises: 010_operation_logs_and_clicks
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa


revision = '011_task_exam_pipeline'
down_revision = '010_operation_logs_and_clicks'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('od_algorithm_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('pose_algorithm_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_tasks_od_algorithm', 'algorithms', ['od_algorithm_id'], ['id']
        )
        batch.create_foreign_key(
            'fk_tasks_pose_algorithm', 'algorithms', ['pose_algorithm_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.drop_constraint('fk_tasks_od_algorithm', type_='foreignkey')
        batch.drop_constraint('fk_tasks_pose_algorithm', type_='foreignkey')
        batch.drop_column('pose_algorithm_id')
        batch.drop_column('od_algorithm_id')
