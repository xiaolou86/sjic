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
    parameter_schema = db.Column(db.JSON)  # scene_presets / ui / default_task_params / publish_meta / origin
    model_id = db.Column(db.Integer, db.ForeignKey('detection_models.id'), nullable=True)
    labels = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def resolved_engine(self):
        return (self.engine or self.type or '').strip()

    def schema_origin(self):
        return ((self.parameter_schema or {}).get('origin') or '').strip()

    def is_system_template(self):
        """系统目录同步的模板：不可直接发布，需派生实例后再绑模型发布。"""
        origin = self.schema_origin()
        if origin == 'system_template':
            return True
        if origin == 'instance':
            return False
        # 兼容旧数据：同 type 中 id 最小的未标记行视为模板，其余视为实例
        from app.utils.algorithm_catalog import get_product
        if get_product(self.type) is None:
            return False
        sibling = (
            Algorithm.query.filter_by(type=self.type)
            .order_by(Algorithm.id.asc())
            .first()
        )
        return sibling is not None and sibling.id == self.id

    def is_published(self):
        publish_meta = (self.parameter_schema or {}).get('publish_meta') or {}
        return bool(publish_meta.get('published', False))

    def ensure_catalog_schema(self, persist=False):
        """补齐缺失的 scene_presets 等（修复手工新建漏拷贝 schema 的实例）。"""
        from sqlalchemy.orm.attributes import flag_modified
        from app.utils.algorithm_catalog import merge_catalog_schema

        if self.schema_origin() == 'system_template' or self.is_system_template():
            origin = 'system_template'
        else:
            origin = 'instance'
        before = dict(self.parameter_schema or {})
        merged = merge_catalog_schema(before, self.resolved_engine(), origin=origin)
        # 明确写回 origin，避免旧实例继续被误判
        if origin == 'instance':
            merged['origin'] = 'instance'
        if merged != before:
            self.parameter_schema = merged
            flag_modified(self, 'parameter_schema')
            if persist:
                db.session.add(self)
            return True
        return False

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
        """同步系统模板；刷新 scene_presets，不覆盖实例、不覆盖模板上的 model_id / publish_meta。"""
        from flask import current_app
        from sqlalchemy.orm.attributes import flag_modified
        from app.utils.algorithm_catalog import PRODUCT_ALGORITHMS

        for data in PRODUCT_ALGORITHMS:
            schema = dict(data.get('parameter_schema') or {})
            schema['origin'] = 'system_template'

            candidates = cls.query.filter_by(type=data['type']).all()
            template = None
            for row in candidates:
                origin = ((row.parameter_schema or {}).get('origin') or '').strip()
                if origin == 'instance':
                    continue
                template = row
                break

            if template:
                old_schema = dict(template.parameter_schema or {})
                old_publish = dict(old_schema.get('publish_meta') or {})
                was_published = bool(old_publish.get('published'))
                # 模板本身不再承载发布状态
                schema.pop('publish_meta', None)
                template.name = data['name']
                template.description = data['description']
                template.engine = data.get('engine') or data['type']
                template.category = data.get('category')
                template.parameter_schema = schema
                flag_modified(template, 'parameter_schema')

                # 历史：模板曾被直接绑模型并发布 → 自动派生一条已发布实例
                if was_published and template.model_id:
                    has_instance = any(
                        ((r.parameter_schema or {}).get('origin') == 'instance')
                        for r in candidates
                        if r.id != template.id
                    )
                    if not has_instance:
                        inst_schema = dict(data.get('parameter_schema') or {})
                        inst_schema = {**inst_schema, 'origin': 'instance', 'publish_meta': old_publish}
                        db.session.add(cls(
                            name=f"{data['name']}（已上架）",
                            type=data['type'],
                            engine=data.get('engine') or data['type'],
                            category=data.get('category'),
                            description=data['description'],
                            parameter_schema=inst_schema,
                            model_id=template.model_id,
                            labels=template.labels,
                        ))
                        # 模型留在实例上；模板清空绑定，避免误用
                        template.model_id = None
            else:
                template = cls(
                    name=data['name'],
                    type=data['type'],
                    engine=data.get('engine') or data['type'],
                    category=data.get('category'),
                    description=data['description'],
                    parameter_schema=schema,
                )
                db.session.add(template)

            # 同 type 的其它行标为实例，并补齐 scene_presets
            db.session.flush()
            refreshed = cls.query.filter_by(type=data['type']).all()
            for row in refreshed:
                if template.id is not None and row.id == template.id:
                    continue
                row.ensure_catalog_schema(persist=False)
                inst_schema = dict(row.parameter_schema or {})
                if inst_schema.get('origin') != 'instance':
                    inst_schema['origin'] = 'instance'
                    row.parameter_schema = inst_schema
                    flag_modified(row, 'parameter_schema')

        db.session.commit()
        current_app.logger.info(
            "Default algorithm templates synced from catalog (%d engine-level).",
            len(PRODUCT_ALGORITHMS),
        )
