"""Operation logs and UI click events

Revision ID: 010_operation_logs_and_clicks
Revises: 009_camera_mount_position
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa


revision = '010_operation_logs_and_clicks'
down_revision = '009_camera_mount_position'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=True),
        sa.Column('action', sa.String(length=20), nullable=True),
        sa.Column('module', sa.String(length=40), nullable=True),
        sa.Column('summary', sa.String(length=255), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_operation_logs_created_at', 'operation_logs', ['created_at'])
    op.create_index('ix_operation_logs_username', 'operation_logs', ['username'])
    op.create_index('ix_operation_logs_action', 'operation_logs', ['action'])
    op.create_index('ix_operation_logs_module', 'operation_logs', ['module'])

    op.create_table(
        'ui_click_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=True),
        sa.Column('page', sa.String(length=120), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ui_click_events_created_at', 'ui_click_events', ['created_at'])
    op.create_index('ix_ui_click_events_page', 'ui_click_events', ['page'])


def downgrade():
    op.drop_index('ix_ui_click_events_page', table_name='ui_click_events')
    op.drop_index('ix_ui_click_events_created_at', table_name='ui_click_events')
    op.drop_table('ui_click_events')
    op.drop_index('ix_operation_logs_module', table_name='operation_logs')
    op.drop_index('ix_operation_logs_action', table_name='operation_logs')
    op.drop_index('ix_operation_logs_username', table_name='operation_logs')
    op.drop_index('ix_operation_logs_created_at', table_name='operation_logs')
    op.drop_table('operation_logs')
