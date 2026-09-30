from datetime import datetime
from app.extensions import db


# pending=待确认, confirmed=属实, false_positive=误报
ALERT_REVIEW_STATUSES = ('pending', 'confirmed', 'false_positive')


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    # 视频源删除后置空，告警和图片仍保留；名称见 camera_name
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=True)
    camera_name = db.Column(db.String(100), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'), nullable=True)
    alert_type = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float)
    image_url = db.Column(db.String(200))
    message = db.Column(db.Text)
    review_status = db.Column(db.String(20), nullable=False, default='pending')
    reviewed_by = db.Column(db.String(64), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.Text, nullable=True)

    def to_dict(self):
        # 构建完整的图片URL
        image_url = None
        if self.image_url:
            if self.image_url.startswith('http'):
                image_url = self.image_url
            else:
                image_url = f'/api/alerts/images/{self.image_url}'

        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'camera_name': self.camera.name if self.camera else (self.camera_name or None),
            'task_id': self.task_id,
            'algorithm_id': self.algorithm_id,
            'alert_type': self.alert_type,
            'confidence': self.confidence,
            'image_url': image_url,
            'message': self.message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'review_status': self.review_status or 'pending',
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'review_note': self.review_note,
        }
