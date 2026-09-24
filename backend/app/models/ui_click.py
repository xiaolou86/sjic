from datetime import datetime
from app.extensions import db


class UiClickEvent(db.Model):
    __tablename__ = 'ui_click_events'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    username = db.Column(db.String(64))
    role = db.Column(db.String(20))
    page = db.Column(db.String(120), nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'username': self.username,
            'role': self.role,
            'page': self.page,
            'label': self.label,
        }
