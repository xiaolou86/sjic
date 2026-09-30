"""Add edge agent version and upgrade status

Revision ID: 014_edge_upgrade_status
Revises: 013_drop_task_notification
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op


revision = '014_edge_upgrade_status'
down_revision = '013_drop_task_notification'
branch_labels = None
depends_on = None

_COLUMNS = (
    ('agent_version', sa.String(length=40)),
    ('upgrade_status', sa.String(length=20)),
    ('upgrade_target_version', sa.String(length=40)),
    ('upgrade_message', sa.String(length=255)),
)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table('edge_nodes'):
        return
    names = {col['name'] for col in insp.get_columns('edge_nodes')}
    with op.batch_alter_table('edge_nodes') as batch:
        for name, column_type in _COLUMNS:
            if name not in names:
                batch.add_column(sa.Column(name, column_type, nullable=True))


def downgrade():
    with op.batch_alter_table('edge_nodes') as batch:
        for name, _column_type in reversed(_COLUMNS):
            batch.drop_column(name)
