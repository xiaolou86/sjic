"""
应用启动入口。
"""
import os


def _use_reloader():
    if os.environ.get('FLASK_ENV') == 'production':
        return False
    flag = os.environ.get('FLASK_DEBUG', '1').strip().lower()
    return flag not in ('0', 'false', 'no')


# 必须在 create_app 之前标记。reloader 父进程也会导入本模块并打开数据库。
if __name__ == '__main__' and _use_reloader():
    os.environ['SJIC_RELOADER'] = '1'

from app import create_app
from app.extensions import socketio

app = create_app()


if __name__ == '__main__':
    debug = _use_reloader()
    socketio.run(
        app,
        host='0.0.0.0',
        port=38881,
        debug=debug,
        use_reloader=debug,
        allow_unsafe_werkzeug=True,
    )