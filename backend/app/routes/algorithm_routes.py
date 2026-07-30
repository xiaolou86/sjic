"""
算法管理路由蓝图
"""
from flask import Blueprint, jsonify, request
from app.extensions import db
from app.models import Algorithm
from app.middleware.auth import token_required
from app.services.license_service import license_service

algorithm_bp = Blueprint('algorithm', __name__)


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

    return jsonify([algorithm.to_dict() for algorithm in algorithms])


@algorithm_bp.route('/api/algorithms', methods=['POST'])
@token_required
def create_algorithm():
    """
    创建新算法定义
    ---
    tags:
      - 算法管理 (Algorithms)
    summary: 注册新的算法类型
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            type:
              type: string
            description:
              type: string
    responses:
      201:
        description: 创建成功
    """
    ok, reason = license_service.ensure_valid()
    if not ok:
      return jsonify({'error': f'License invalid: {reason}'}), 403

    data = request.json
    algorithm_type = data.get('type')
    allowed, deny_reason = license_service.is_algorithm_allowed(algorithm_type)
    if not allowed:
      return jsonify({'error': f'Algorithm not allowed by license: {deny_reason}'}), 403

    algorithm = Algorithm(**data)
    db.session.add(algorithm)
    db.session.commit()
    return jsonify(algorithm.to_dict()), 201


@algorithm_bp.route('/api/algorithms/<int:alg_id>', methods=['PUT'])
@token_required
def update_algorithm(alg_id):
    """更新算法模板"""
    data = request.json
    algorithm = Algorithm.query.get_or_404(alg_id)
    
    for key, value in data.items():
        if hasattr(algorithm, key):
            setattr(algorithm, key, value)
            
    db.session.commit()
    return jsonify(algorithm.to_dict())


@algorithm_bp.route('/api/algorithms/<int:alg_id>', methods=['DELETE'])
@token_required
def delete_algorithm(alg_id):
    """删除算法模板"""
    algorithm = Algorithm.query.get_or_404(alg_id)
    db.session.delete(algorithm)
    db.session.commit()
    return '', 204
