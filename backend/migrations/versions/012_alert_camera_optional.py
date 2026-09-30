"""Keep alerts after a camera is deleted

Revision ID: 012_alert_camera_optional
Revises: 011_task_exam_pipeline
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

from app.utils.db_compat import apply_alert_camera_optional


revision = '012_alert_camera_optional'
down_revision = '011_task_exam_pipeline'
branch_labels = None
depends_on = None


def upgrade():
    apply_alert_camera_optional(op, op.get_bind())


def downgrade():
    with op.batch_alter_table('alerts') as batch:
        batch.alter_column('camera_id', existing_type=sa.Integer(), nullable=False)
        batch.drop_column('camera_name')
