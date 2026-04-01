"""
日志管理路由蓝图
"""
from flask import Blueprint, jsonify, request
from app.extensions import db
from app.models import Log
from app.middleware.auth import token_required

log_bp = Blueprint('log', __name__)


@log_bp.route('/api/logs', methods=['GET'])
@token_required
def get_logs():
    """
    获取系统日志
    ---
    tags:
      - 日志管理 (Logs)
    summary: 分页获取后台日志
    security:
      - APIKeyHeader: []
    parameters:
      - name: page
        in: query
        type: integer
        description: 页码
      - name: per_page
        in: query
        type: integer
        description: 每页数量
    responses:
      200:
        description: 分页日志列表
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    logs = Log.query.order_by(Log.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'items': [log.to_dict() for log in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': logs.page
    })


@log_bp.route('/api/logs', methods=['DELETE'])
@token_required
def clear_logs():
    """
    清除所有日志
    ---
    tags:
      - 日志管理 (Logs)
    summary: 清空全表日志数据
    security:
      - APIKeyHeader: []
    responses:
      204:
        description: 清除成功
    """
    Log.query.delete()
    db.session.commit()
    return '', 204


@log_bp.route('/api/logs/delete/<int:id>', methods=['DELETE'])
@token_required
def delete_log(id):
    """
    删除单条日志
    ---
    tags:
      - 日志管理 (Logs)
    summary: 删除指定ID的日志
    security:
      - APIKeyHeader: []
    parameters:
      - name: id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 删除成功
    """
    log = Log.query.get(id)
    db.session.delete(log)
    db.session.commit()
    return jsonify({"status": "success"})
