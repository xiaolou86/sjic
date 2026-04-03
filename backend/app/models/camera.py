from datetime import datetime
from flask import current_app
from app.extensions import db
from werkzeug.utils import secure_filename
from config import Config
import os

class Camera(db.Model):
    __tablename__ = 'cameras'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    alerts = db.relationship('Alert', backref='camera', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

    def get_rtsp_url(self):
        file = str(self.url).strip()
        current_app.logger.info(f"Camera Source: {file}")
        
        # 1. 常见流媒体协议 (RTSP / RTMP / HTTP 网络流)
        if any(file.startswith(p) for p in ['rtsp://', 'rtmp://', 'http://', 'https://']):
            return file
            
        # 2. 本地 USB 摄像头设备索引 (如 '0', '1')
        if file.isdigit():
            return int(file) # OpenCV 需要整型来进行本地设备采集
            
        # 3. Linux/边缘设备驱动路径 (如 '/dev/video0')
        if file.startswith('/dev/'):
            return file
            
        # 4. 保留兼容：如果是纯前端上传的裸文件名称（旧版云端推理遗留）
        # 因现在是边缘推理，如果需要下发 MP4 建议输入边缘机器绝对路径，或使用网络流。
        if not ('/' in file or '\\' in file):
            filename = secure_filename(file)
            file_path = os.path.join(Config.VIDEO_FOLDER, filename)
            # 注意: 如果发送给异地边缘端，边缘端是无法访问云端本机 C 盘/D 盘物理路径的。
            # 这里保留仅为了容错或后续搭建回源代理。
            return file_path
            
        return file
