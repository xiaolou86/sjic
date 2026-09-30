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


if __name__ == '__main__':
    main()
