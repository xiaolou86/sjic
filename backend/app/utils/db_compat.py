import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app.extensions import db


# 历史列已由 Alembic revision 003 收编；此处保留空列表，仅供极老库应急。
COMPAT_COLUMNS = []


def ensure_legacy_schema(app):
    """为旧数据库补齐新版本增加的列。"""

    def has_table(table_name):
        try:
            return inspect(db.engine).has_table(table_name)
        except Exception:
            return False

    def has_column(table_name, column_name):
        try:
            columns = inspect(db.engine).get_columns(table_name)
            return any(col["name"] == column_name for col in columns)
        except Exception:
            return False

    app.logger.info(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")

    with db.engine.begin() as connection:
        for table_name, column_name, column_type in COMPAT_COLUMNS:
            if not has_table(table_name):
                app.logger.warning(f"Skip legacy migration: table {table_name} not found")
                continue

            if has_column(table_name, column_name):
                continue

            app.logger.warning(
                f"Auto-migrating legacy database: add column {table_name}.{column_name}"
            )
            connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            )


def apply_alert_camera_optional(operations, bind):
    """告警的 camera_id 改为可空，并补上 camera_name，便于视频源删除后保留历史告警。"""
    insp = inspect(bind)
    if not insp.has_table('alerts'):
        return
    cols = {col['name']: col for col in insp.get_columns('alerts')}
    if 'camera_id' not in cols:
        return
    needs_name = 'camera_name' not in cols
    needs_null = not cols['camera_id'].get('nullable', False)
    if not needs_name and not needs_null:
        return
    with operations.batch_alter_table('alerts') as batch:
        if needs_name:
            batch.add_column(sa.Column('camera_name', sa.String(length=100), nullable=True))
        if needs_null:
            batch.alter_column('camera_id', existing_type=sa.Integer(), nullable=True)


def ensure_alert_camera_optional():
    """已有库在启动或删除视频源时补齐，不依赖是否已经执行过迁移。"""
    engine = db.engine
    if not inspect(engine).has_table('alerts'):
        return
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        apply_alert_camera_optional(Operations(context), connection)

