"""
算法管理路由蓝图

系统模板（origin=system_template）：目录同步，不可发布。
上架实例（origin=instance）：从模板派生，绑定模型后发布，任务侧可见。
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.middleware.auth import get_token_payload, role_required, token_required
from app.models import Algorithm
from app.services.license_service import license_service

algorithm_bp = Blueprint('algorithm', __name__)


def _is_published(algorithm):
    return algorithm.is_published()


def _serialize_algorithm(algorithm, include_internal=False):
    # 读时补齐 scene_presets，避免旧实例任务页看不到场景
    changed = algorithm.ensure_catalog_schema(persist=False)
    if changed:
        try:
            db.session.add(algorithm)
            db.session.commit()
        except Exception:
            db.session.rollback()

    data = algorithm.to_dict()
    schema = algorithm.parameter_schema or {}
    publish_meta = schema.get('publish_meta', {})
    data['published'] = bool(publish_meta.get('published', False))
    data['published_at'] = publish_meta.get('published_at')
    data['is_system_template'] = algorithm.is_system_template()
    data['origin'] = schema.get('origin') or ('system_template' if data['is_system_template'] else 'instance')
    data['needs_model'] = True
    try:
        from app.utils.algorithm_catalog import engine_needs_model
        data['needs_model'] = engine_needs_model(algorithm.resolved_engine())
    except Exception:
        pass

    if not include_internal:
        data.pop('model_id', None)

    return data


@algorithm_bp.route('/api/algorithms/catalog', methods=['GET'])
@token_required
def get_algorithm_catalog():
    """产品算法 / 引擎 / 场景预设静态目录。"""
    from app.utils.algorithm_catalog import catalog_for_api
    return jsonify(catalog_for_api())


@algorithm_bp.route('/api/algorithms', methods=['GET'])
@token_required
def get_algorithms():
    """获取算法列表（模板 + 实例；客户仅见已发布实例）。"""
    ok, reason = license_service.ensure_valid()
    if not ok:
        return jsonify({'error': f'License invalid: {reason}'}), 403

    status = license_service.get_status()
    allowed_types = status.get('allowed_algorithms') or []

    algorithms = Algorithm.query.order_by(Algorithm.id.asc()).all()
    if allowed_types:
        algorithms = [a for a in algorithms if a.type in allowed_types]

    payload = get_token_payload() or {}
    is_vendor = payload.get('role') == 'vendor'
    if not is_vendor:
        # 客户：只看已发布的上架实例（系统模板不可见）
        algorithms = [
            a for a in algorithms
            if (not a.is_system_template()) and _is_published(a)
        ]

    return jsonify([
        _serialize_algorithm(algorithm, include_internal=is_vendor)
        for algorithm in algorithms
    ])


@algorithm_bp.route('/api/algorithms', methods=['POST'])
@token_required
@role_required('vendor')
def create_algorithm():
    """创建上架实例（建议走 /derive；本接口也会从目录补齐 schema）。"""
    ok, reason = license_service.ensure_valid()
    if not ok:
        return jsonify({'error': f'License invalid: {reason}'}), 403

    data = request.json or {}
    algorithm_type = data.get('type')
    allowed, deny_reason = license_service.is_algorithm_allowed(algorithm_type)
    if not allowed:
        return jsonify({'error': f'Algorithm not allowed by license: {deny_reason}'}), 403

    from app.utils.algorithm_catalog import get_product, merge_catalog_schema

    if not data.get('engine'):
        product = get_product(algorithm_type) if algorithm_type else None
        data['engine'] = (product or {}).get('engine') or algorithm_type
    if not data.get('category'):
        product = get_product(algorithm_type) if algorithm_type else None
        if product:
            data['category'] = product.get('category')

    engine = data.get('engine') or algorithm_type
    schema = merge_catalog_schema(data.get('parameter_schema') or {}, engine, origin='instance')
    schema['origin'] = 'instance'
    # 新实例默认未发布
    schema.pop('publish_meta', None)

    allowed_keys = {
        'name', 'type', 'engine', 'category',
        'description', 'model_id', 'labels',
    }
    payload = {k: v for k, v in data.items() if k in allowed_keys}
    payload['parameter_schema'] = schema
    algorithm = Algorithm(**payload)
    db.session.add(algorithm)
    db.session.commit()
    return jsonify(_serialize_algorithm(algorithm, include_internal=True)), 201


@algorithm_bp.route('/api/algorithms/<int:alg_id>/derive', methods=['POST'])
@token_required
@role_required('vendor')
def derive_algorithm(alg_id):
    """从系统模板派生可上架实例（拷贝 scene_presets，随后绑模型并发布）。"""
    ok, reason = license_service.ensure_valid()
    if not ok:
        return jsonify({'error': f'License invalid: {reason}'}), 403

    template = Algorithm.query.get_or_404(alg_id)
    if not template.is_system_template():
        return jsonify({'error': 'Only system templates can be derived'}), 400

    allowed, deny_reason = license_service.is_algorithm_allowed(template.type)
    if not allowed:
        return jsonify({'error': f'Algorithm not allowed by license: {deny_reason}'}), 403

    from app.utils.algorithm_catalog import merge_catalog_schema

    body = request.json or {}
    schema = merge_catalog_schema(template.parameter_schema or {}, template.resolved_engine(), origin='instance')
    schema['origin'] = 'instance'
    schema.pop('publish_meta', None)

    name = (body.get('name') or '').strip() or f"{template.name}（上架）"
    instance = Algorithm(
        name=name,
        type=template.type,
        engine=template.resolved_engine(),
        category=template.category,
        description=body.get('description') if body.get('description') is not None else template.description,
        parameter_schema=schema,
        model_id=body.get('model_id') or None,
        labels=body.get('labels') if body.get('labels') is not None else (template.labels or []),
    )
    db.session.add(instance)
    db.session.commit()
    return jsonify(_serialize_algorithm(instance, include_internal=True)), 201


@algorithm_bp.route('/api/algorithms/<int:alg_id>', methods=['PUT'])
@token_required
@role_required('vendor')
def update_algorithm(alg_id):
    """更新算法（模板仅允许改描述等；实例可绑模型）。"""
    data = request.json or {}
    algorithm = Algorithm.query.get_or_404(alg_id)

    if algorithm.is_system_template():
        # 模板：禁止绑模型/改 type/engine，仅允许名称描述微调
        for key in ('name', 'description', 'category'):
            if key in data:
                setattr(algorithm, key, data[key])
    else:
        for key, value in data.items():
            if key in ('id', 'created_at', 'parameter_schema'):
                continue
            if hasattr(algorithm, key):
                setattr(algorithm, key, value)
        algorithm.ensure_catalog_schema(persist=False)

    db.session.commit()
    return jsonify(_serialize_algorithm(algorithm, include_internal=True))


@algorithm_bp.route('/api/algorithms/<int:alg_id>', methods=['DELETE'])
@token_required
@role_required('vendor')
def delete_algorithm(alg_id):
    """删除上架实例；系统模板不可删。"""
    algorithm = Algorithm.query.get_or_404(alg_id)
    if algorithm.is_system_template():
        return jsonify({'error': 'System templates cannot be deleted'}), 400
    db.session.delete(algorithm)
    db.session.commit()
    return '', 204


@algorithm_bp.route('/api/algorithms/<int:alg_id>/publish', methods=['POST'])
@token_required
@role_required('vendor')
def publish_algorithm(alg_id):
    """发布上架实例：发布后对客户与任务可见。系统模板不可发布。"""
    from app.utils.algorithm_catalog import engine_needs_model

    algorithm = Algorithm.query.get_or_404(alg_id)

    if algorithm.is_system_template():
        return jsonify({
            'error': 'System templates cannot be published. Derive an instance, bind a model, then publish.',
        }), 400

    algorithm.ensure_catalog_schema(persist=False)

    if engine_needs_model(algorithm.resolved_engine()) and not algorithm.model_id:
        return jsonify({'error': 'Please bind a model in edit before publish'}), 400

    schema = dict(algorithm.parameter_schema or {})
    schema['origin'] = 'instance'
    schema['publish_meta'] = {
        'published': True,
        'published_at': datetime.now().isoformat(),
    }
    algorithm.parameter_schema = schema
    flag_modified(algorithm, 'parameter_schema')

    db.session.commit()

    return jsonify({
        'message': 'Algorithm published',
        'algorithm': _serialize_algorithm(algorithm, include_internal=True),
        'publish_meta': schema['publish_meta'],
    }), 200
