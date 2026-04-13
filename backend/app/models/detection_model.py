from datetime import datetime
from app.extensions import db

class DetectionModel(db.Model):
    __tablename__ = 'detection_models'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    path = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # labelmap: 绑定模型输出类别的 ID->名称 映射
    # 推荐格式：[{ "id": 0, "name": "person" }, ...]
    labelmap = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'description': self.description,
            'labelmap': self.labelmap,
            'created_at': self.created_at.isoformat()
        }
