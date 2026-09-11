"""
告警管理路由蓝图
"""
from flask import Blueprint, jsonify, request, send_from_directory, current_app
from app.extensions import db, socketio
from app.models import Alert, Camera
from app.middleware.auth import token_required

alert_bp = Blueprint('alert', __name__)


@alert_bp.route('/api/alerts', methods=['GET'])
@token_required
def get_alerts():
    """
    获取告警记录
    ---
    tags:
      - 告警管理 (Alerts)
    summary: 分页获取告警列表
    security:
      - APIKeyHeader: []
    parameters:
      - name: page
        in: query
        type: integer
        description: 页码，默认 1
      - name: per_page
        in: query
        type: integer
        description: 每页数量，默认 10
    responses:
      200:
        description: 告警列表和分页信息
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        # 获取分页数据
        pagination = Alert.query.order_by(Alert.timestamp.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        alerts = pagination.items

        return jsonify({
            'items': [alert.to_dict() for alert in alerts],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })

    except Exception as e:
        current_app.logger.error(f"Error getting alerts: {str(e)}")
        return jsonify({'error': str(e)}), 500


@alert_bp.route('/api/alerts', methods=['POST'])
@token_required
def create_alert():
    """
    创建新告警 (后端直接调用，非常规使用)
    ---
    tags:
      - 告警管理 (Alerts)
    summary: 手动创建告警
    security:
      - APIKeyHeader: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            camera_id:
              type: integer
            alert_type:
              type: string
            confidence:
              type: number
            image_url:
              type: string
            message:
              type: string
    responses:
      201:
        description: 创建成功
    """
    data = request.json

    camera = Camera.query.get(data['camera_id'])
    if not camera:
        return jsonify({'error': 'Camera not found'}), 404

    alert = Alert(
        camera_id=data['camera_id'],
        alert_type=data['alert_type'],
        confidence=data.get('confidence'),
        image_url=data.get('image_url'),
        message=data.get('message'),
    )

    db.session.add(alert)
    db.session.commit()

    # 通过WebSocket发送实时告警
    socketio.emit('new_alert', alert.to_dict())

    return jsonify(alert.to_dict()), 201


@alert_bp.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@token_required
def delete_alert(alert_id):
    """
    删除告警记录
    ---
    tags:
      - 告警管理 (Alerts)
    summary: 删除指定告警
    security:
      - APIKeyHeader: []
    parameters:
      - name: alert_id
        in: path
        type: integer
        required: true
        description: 告警ID
    responses:
      204:
        description: 删除成功
    """
    alert = Alert.query.get_or_404(alert_id)
    db.session.delete(alert)
    db.session.commit()
    return '', 204


@alert_bp.route('/api/alerts/images/<path:filename>')
def get_alert_image(filename):
    """
    获取告警图片
    ---
    tags:
      - 告警管理 (Alerts)
    summary: 下载或查看告警图片
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: 图片文件名
    responses:
      200:
        description: 成功返回图片流
      404:
        description: 图片未找到
    """
    try:
        return send_from_directory(current_app.config['ALERT_FOLDER'], filename)
    except Exception as e:
        current_app.logger.error(f"Error getting alert image: {str(e)}")
        return jsonify({'error': str(e)}), 404
