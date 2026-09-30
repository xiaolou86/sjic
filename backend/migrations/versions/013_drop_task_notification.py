"""Drop unused task notification switch

Revision ID: 013_drop_task_notification
Revises: 012_alert_camera_optional
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op


revision = '013_drop_task_notification'
down_revision = '012_alert_camera_optional'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table('tasks'):
        return
    names = {col['name'] for col in insp.get_columns('tasks')}
    if 'notificationEnabled' not in names:
        return
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('notificationEnabled')


def downgrade():
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('notificationEnabled', sa.Boolean(), nullable=True))
