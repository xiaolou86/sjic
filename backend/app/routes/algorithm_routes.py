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
    """获取算法"""
    algorithms = Algorithm.query.all()
    return jsonify([algorithm.to_dict() for algorithm in algorithms])


@algorithm_bp.route('/api/algorithms', methods=['POST'])
@token_required
def create_algorithm():
    """创建新算法"""
    data = request.json
    algorithm = Algorithm(**data)
    db.session.add(algorithm)
    db.session.commit()
    return jsonify(algorithm.to_dict()), 201
