"""
日志管理路由蓝图
"""
from flask import Blueprint, jsonify, request
from app.extensions import db
from app.models import Log, OperationLog
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


@log_bp.route('/api/operation-logs', methods=['GET'])
@token_required
def get_operation_logs():
    """分页查询创建、修改、删除、登录、登出等操作日志。"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int) or 20, 100)
    action = (request.args.get('action') or '').strip()
    module = (request.args.get('module') or '').strip()
    keyword = (request.args.get('keyword') or '').strip()

    query = OperationLog.query
    if action:
        query = query.filter(OperationLog.action == action)
    if module:
        query = query.filter(OperationLog.module == module)
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(
            db.or_(
                OperationLog.summary.like(like),
                OperationLog.username.like(like),
            )
        )

    logs = query.order_by(OperationLog.created_at.desc(), OperationLog.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'items': [item.to_dict() for item in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': logs.page,
    })
