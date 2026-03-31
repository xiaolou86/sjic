"""
Flask 扩展实例化模块。
所有扩展在此创建实例，在 create_app() 中通过 init_app() 绑定到应用。
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_sock import Sock

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
cors = CORS()
sock = Sock()
