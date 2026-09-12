"""
算法管理路由蓝图
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.middleware.auth import get_token_payload, role_required, token_required
from app.models import Algorithm
from app.services.license_service import license_service

algorithm_bp = Blueprint('algorithm', __name__)


def _is_published(algorithm):
    schema = algorithm.parameter_schema or {}
    publish_meta = schema.get('publish_meta', {})
    return bool(publish_meta.get('published', False))


def _serialize_algorithm(algorithm, include_internal=False):
    data = algorithm.to_dict()
    schema = algorithm.parameter_schema or {}
    publish_meta = schema.get('publish_meta', {})
    data['published'] = bool(publish_meta.get('published', False))
    data['published_at'] = publish_meta.get('published_at')
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
    """产品算法 / 引擎 / 摄像头位静态目录（前端下拉与任务引导）。"""
    from app.utils.algorithm_catalog import catalog_for_api
    return jsonify(catalog_for_api())


@algorithm_bp.route('/api/algorithms', methods=['GET'])
@token_required
def get_algorithms():
    """
    获取所有可用算法
    ---
    tags:
      - 算法管理 (Algorithms)
    summary: 获取可用算法列表
    security:
      - APIKeyHeader: []
    responses:
      200:
        description: 算法配置列表
    """
    ok, reason = license_service.ensure_valid()
    if not ok:
        return jsonify({'error': f'License invalid: {reason}'}), 403

    status = license_service.get_status()
    allowed_types = status.get('allowed_algorithms') or []

    algorithms = Algorithm.query.all()
    if allowed_types:
        algorithms = [a for a in algorithms if a.type in allowed_types]

    payload = get_token_payload() or {}
    is_vendor = payload.get('role') == 'vendor'
    if not is_vendor:
        algorithms = [a for a in algorithms if _is_published(a)]

    return jsonify([
        _serialize_algorithm(algorithm, include_internal=is_vendor)
        for algorithm in algorithms
    ])


@algorithm_bp.route('/api/algorithms', methods=['POST'])
@token_required
@role_required('vendor')
def create_algorithm():
    """创建新算法定义"""
    ok, reason = license_service.ensure_valid()
    if not ok:
        return jsonify({'error': f'License invalid: {reason}'}), 403

    data = request.json or {}
    algorithm_type = data.get('type')
    allowed, deny_reason = license_service.is_algorithm_allowed(algorithm_type)
    if not allowed:
        return jsonify({'error': f'Algorithm not allowed by license: {deny_reason}'}), 403

    # 未显式传 engine 时：目录有则取目录，否则 type 即引擎
    if not data.get('engine'):
        from app.utils.algorithm_catalog import get_product
        product = get_product(algorithm_type) if algorithm_type else None
        data['engine'] = (product or {}).get('engine') or algorithm_type
    if not data.get('category'):
        from app.utils.algorithm_catalog import get_product
        product = get_product(algorithm_type) if algorithm_type else None
        if product:
            data['category'] = product.get('category')

    allowed_keys = {
        'name', 'type', 'engine', 'category',
        'description', 'parameter_schema', 'model_id', 'labels',
    }
    payload = {k: v for k, v in data.items() if k in allowed_keys}
    algorithm = Algorithm(**payload)
    db.session.add(algorithm)
    db.session.commit()
    return jsonify(_serialize_algorithm(algorithm, include_internal=True)), 201


@algorithm_bp.route('/api/algorithms/<int:alg_id>', methods=['PUT'])
@token_required
@role_required('vendor')
def update_algorithm(alg_id):
    """更新算法模板（含模型绑定）。"""
    data = request.json or {}
    algorithm = Algorithm.query.get_or_404(alg_id)

    for key, value in data.items():
        if hasattr(algorithm, key):
            setattr(algorithm, key, value)

    db.session.commit()
    return jsonify(_serialize_algorithm(algorithm, include_internal=True))


@algorithm_bp.route('/api/algorithms/<int:alg_id>', methods=['DELETE'])
@token_required
@role_required('vendor')
def delete_algorithm(alg_id):
    """删除算法模板"""
    algorithm = Algorithm.query.get_or_404(alg_id)
    db.session.delete(algorithm)
    db.session.commit()
    return '', 204


@algorithm_bp.route('/api/algorithms/<int:alg_id>/publish', methods=['POST'])
@token_required
@role_required('vendor')
def publish_algorithm(alg_id):
    """发布算法：发布后才对客户与任务可见。"""
    from app.utils.algorithm_catalog import engine_needs_model

    algorithm = Algorithm.query.get_or_404(alg_id)

    if engine_needs_model(algorithm.resolved_engine()) and not algorithm.model_id:
        return jsonify({'error': 'Please bind a model in edit before publish'}), 400

    schema = algorithm.parameter_schema or {}
    schema['publish_meta'] = {
        'published': True,
        'published_at': datetime.now().isoformat(),
    }
    algorithm.parameter_schema = schema
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(algorithm, 'parameter_schema')

    db.session.commit()

    return jsonify({
        'message': 'Algorithm published',
        'algorithm': _serialize_algorithm(algorithm, include_internal=True),
        'publish_meta': schema['publish_meta'],
    }), 200
