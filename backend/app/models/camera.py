from datetime import datetime
from flask import current_app
from app.extensions import db
from werkzeug.utils import secure_filename
from config import Config
import os

class Camera(db.Model):
    __tablename__ = 'cameras'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 机位用名称体现，如「1号考生位」
    url = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
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
        
        if any(file.startswith(p) for p in ['rtsp://', 'rtmp://', 'http://', 'https://']):
            return file
            
        if file.isdigit():
            return int(file)
            
        if file.startswith('/dev/'):
            return file
            
        if not ('/' in file or '\\' in file):
            filename = secure_filename(file)
            file_path = os.path.join(Config.VIDEO_FOLDER, filename)
            return file_path
            
        return file
