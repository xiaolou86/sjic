"""升级时执行数据库迁移。发版包里本文件是 migrate_entry.pyc。"""
import os

os.environ.setdefault('SJIC_MIGRATE_ONLY', '1')


def main():
    from app.utils.pyc_alembic import install_pyc_env_loader
    install_pyc_env_loader()
    from app import create_app
    from flask_migrate import upgrade

    app = create_app()
    with app.app_context():
        upgrade()
        if not _current_revision():
            raise RuntimeError(
                '数据库迁移没有写入版本号。迁移脚本未被识别，表不会被创建'
            )


def _current_revision():
    from alembic.runtime.migration import MigrationContext
    from app.extensions import db

    with db.engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


if __name__ == '__main__':
    main()
