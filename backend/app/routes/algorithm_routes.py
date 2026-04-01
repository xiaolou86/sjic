"""
算法管理路由蓝图
"""
from flask import Blueprint, jsonify, request
from app.extensions import db
from app.models import Algorithm
from app.middleware.auth import token_required

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
    algorithms = Algorithm.query.all()
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
    data = request.json
    algorithm = Algorithm(**data)
    db.session.add(algorithm)
    db.session.commit()
    return jsonify(algorithm.to_dict()), 201
