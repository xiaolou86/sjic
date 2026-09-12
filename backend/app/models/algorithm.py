from app.extensions import db
from datetime import datetime


class Algorithm(db.Model):
    __tablename__ = 'algorithms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # 算法唯一标识（授权 / 任务绑定）；驾考侧通常与 engine 相同
    type = db.Column(db.String(50), nullable=False)
    # 边缘引擎标识（ALGORITHM_REGISTRY）
    engine = db.Column(db.String(50), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text)
    parameter_schema = db.Column(db.JSON)  # rule_types / scene_presets / default_task_params / publish_meta
    model_id = db.Column(db.Integer, db.ForeignKey('detection_models.id'), nullable=True)
    labels = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def resolved_engine(self):
        return (self.engine or self.type or '').strip()

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'engine': self.resolved_engine(),
            'category': self.category,
            'description': self.description,
            'parameter_schema': self.parameter_schema,
            'model_id': self.model_id,
            'labels': self.labels,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def get_algorithm(cls, algorithm_type):
        algorithm = cls.query.filter_by(type=algorithm_type).first()
        if not algorithm:
            raise ValueError(f"Unknown algorithm type: {algorithm_type}")
        return algorithm

    @classmethod
    def get_algorithm_by_id(cls, algorithm_id):
        algorithm = cls.query.get(algorithm_id)
        if not algorithm:
            raise ValueError(f"Unknown algorithm id: {algorithm_id}")
        return algorithm

    @classmethod
    def initialize_default_algorithms(cls):
        """同步引擎级算法模板；刷新 scene_presets，不覆盖 publish_meta / model_id。"""
        from flask import current_app
        from sqlalchemy.orm.attributes import flag_modified
        from app.utils.algorithm_catalog import PRODUCT_ALGORITHMS

        for data in PRODUCT_ALGORITHMS:
            existing = cls.query.filter_by(type=data['type']).first()
            schema = dict(data.get('parameter_schema') or {})

            if existing:
                old_schema = dict(existing.parameter_schema or {})
                if 'publish_meta' in old_schema:
                    schema['publish_meta'] = old_schema['publish_meta']
                existing.name = data['name']
                existing.description = data['description']
                existing.engine = data.get('engine') or data['type']
                existing.category = data.get('category')
                existing.parameter_schema = schema
                flag_modified(existing, 'parameter_schema')
            else:
                db.session.add(cls(
                    name=data['name'],
                    type=data['type'],
                    engine=data.get('engine') or data['type'],
                    category=data.get('category'),
                    description=data['description'],
                    parameter_schema=schema,
                ))

        db.session.commit()
        current_app.logger.info(
            "Default algorithms synced from catalog (%d engine-level).",
            len(PRODUCT_ALGORITHMS),
        )
