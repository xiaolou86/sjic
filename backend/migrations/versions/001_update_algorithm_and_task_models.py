"""Update algorithm and task models

Revision ID: 001
Revises: 000
Create Date: 2025-02-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = '000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.alter_column(
            'parameters',
            new_column_name='parameter_schema',
            existing_type=sa.JSON(),
        )

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('algorithm_parameters', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('algorithm_parameters')

    with op.batch_alter_table('algorithms', schema=None) as batch_op:
        batch_op.alter_column(
            'parameter_schema',
            new_column_name='parameters',
            existing_type=sa.JSON(),
        )
