from datetime import datetime
from app.extensions import db


class OperationLog(db.Model):
    __tablename__ = 'operation_logs'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    username = db.Column(db.String(64), index=True)
    role = db.Column(db.String(20))
    action = db.Column(db.String(20), index=True)
    module = db.Column(db.String(40), index=True)
    summary = db.Column(db.String(255), nullable=False)
    success = db.Column(db.Boolean, default=True)
    status_code = db.Column(db.Integer)
    ip = db.Column(db.String(64))

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'username': self.username,
            'role': self.role,
            'action': self.action,
            'module': self.module,
            'summary': self.summary,
            'success': self.success,
            'status_code': self.status_code,
            'ip': self.ip,
        }
