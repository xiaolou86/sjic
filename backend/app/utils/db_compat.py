from sqlalchemy import inspect, text

from app.extensions import db


COMPAT_COLUMNS = [
    # 节点可绑定多个视频源
    ("edge_nodes", "bound_cameras", "TEXT"),
    # 模型 labelmap
    ("detection_models", "labelmap", "TEXT"),
]


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

