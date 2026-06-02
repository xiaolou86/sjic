"""Edge nodes table and edge-era columns (replaces db_compat / patch_db)

Revision ID: 003
Revises: 002
Create Date: 2026-05-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'edge_nodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('mac_address', sa.String(length=30), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('architecture', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('hardware_status', sa.JSON(), nullable=True),
        sa.Column('bound_cameras', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mac_address'),
    )

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edge_node_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('run_status', sa.String(length=20), nullable=True, server_default='stopped')
        )
        batch_op.create_foreign_key(
            'fk_tasks_edge_node_id',
            'edge_nodes',
            ['edge_node_id'],
            ['id'],
        )

    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('model_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('labels', sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            'fk_algorithms_model_id',
            'detection_models',
            ['model_id'],
            ['id'],
        )

    with op.batch_alter_table('detection_models', schema=None) as batch_op:
        batch_op.add_column(sa.Column('labelmap', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('detection_models', schema=None) as batch_op:
        batch_op.drop_column('labelmap')

    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.drop_constraint('fk_algorithms_model_id', type_='foreignkey')
        batch_op.drop_column('labels')
        batch_op.drop_column('model_id')

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tasks_edge_node_id', type_='foreignkey')
        batch_op.drop_column('run_status')
        batch_op.drop_column('edge_node_id')

    op.drop_table('edge_nodes')
