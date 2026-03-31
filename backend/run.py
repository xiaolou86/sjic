"""
应用启动入口。
"""
from app import create_app
from app.extensions import db, socketio

app = create_app()


def init_db():
    app.app_context().push()
    db.create_all()


if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=38881, debug=True, allow_unsafe_werkzeug=True)