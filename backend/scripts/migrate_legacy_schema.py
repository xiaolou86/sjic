import os
import sys

# 将应用根目录添加到 sys.path，以便能够导入 app 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.utils.db_compat import ensure_legacy_schema


def main():
    app = create_app()
    with app.app_context():
        ensure_legacy_schema(app)
        print("Legacy schema migration completed.")


if __name__ == "__main__":
    main()

