from app.extensions import db
from datetime import datetime

class Algorithm(db.Model):
    __tablename__ = 'algorithms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 算法类型标识
    description = db.Column(db.Text)
    parameter_schema = db.Column(db.JSON)  # 参数的schema定义
    model_id = db.Column(db.Integer, db.ForeignKey('detection_models.id'), nullable=True)
    labels = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 删除 SQLAlchemy 的多态映射，因为后端现在纯粹只做数据中台，不再需要分别派生子类。
    # 所有的算法对象对于 Flask 后端来说，都只是一条纯记录。
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'description': self.description,
            'parameter_schema': self.parameter_schema,
            'model_id': self.model_id,
            'labels': self.labels,
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def get_algorithm(cls, algorithm_type):
        """获取算法实例"""
        algorithm = cls.query.filter_by(type=algorithm_type).first()
        if not algorithm:
            raise ValueError(f"Unknown algorithm type: {algorithm_type}")
        return algorithm 
    
    @classmethod
    def get_algorithm_by_id(cls, algorithm_id):
        """获取算法实例"""
        algorithm = cls.query.get(algorithm_id)
        if not algorithm:
            raise ValueError(f"Unknown algorithm id: {algorithm_id}")
        return algorithm 
        
    @classmethod
    def initialize_default_algorithms(cls):
        """初始化系统默认支持的边缘端算法"""
        from flask import current_app
        from app.utils.object_detection_schema import OBJECT_DETECTION_RULE_TYPES

        algorithms_data = [
            {'type': 'object_detection', 'name': '目标通用检测', 'desc': '标准通用目标检测'},
            {'type': 'belt_broken', 'name': '皮带表面故障检测', 'desc': '检测皮带表面破损划伤'},
            {'type': 'belt_deviation_detection', 'name': '皮带跑偏检测', 'desc': '基于边缘检测和截面分析的皮带跑偏监测'},
            {'type': 'belt_broken_series', 'name': '皮带撕裂与磨损检测', 'desc': '皮带连续撕裂检测'},
            {'type': 'belt_broken_high', 'name': '高精度皮带表面撕裂检测', 'desc': '高精度皮带表面撕裂检测'}
        ]
        
        for data in algorithms_data:
            existing = cls.query.filter_by(type=data['type']).first()
            if not existing:
                new_algo = cls(
                    name=data['name'],
                    type=data['type'],
                    description=data['desc']
                )
                db.session.add(new_algo)
                existing = new_algo
            else:
                existing.name = data['name']
                existing.description = data['desc']

            if data['type'] == 'object_detection':
                schema = dict(existing.parameter_schema or {})
                schema['rule_types'] = OBJECT_DETECTION_RULE_TYPES
                existing.parameter_schema = schema
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(existing, 'parameter_schema')
                
        db.session.commit()
        current_app.logger.info("Default algorithms seamlessly initialized.")