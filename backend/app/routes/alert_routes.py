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
    """获取告警记录，支持分页"""
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
    """创建新告警"""
    data = request.json

    camera = Camera.query.get(data['camera_id'])
    if not camera:
        return jsonify({'error': 'Camera not found'}), 404

    alert = Alert(
        camera_id=data['camera_id'],
        alert_type=data['alert_type'],
        confidence=data.get('confidence'),
        image_url=data.get('image_url')
    )

    db.session.add(alert)
    db.session.commit()

    # 通过WebSocket发送实时告警
    socketio.emit('new_alert', alert.to_dict())

    return jsonify(alert.to_dict()), 201


@alert_bp.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@token_required
def delete_alert(alert_id):
    """删除告警记录"""
    alert = Alert.query.get_or_404(alert_id)
    db.session.delete(alert)
    db.session.commit()
    return '', 204


@alert_bp.route('/api/alerts/images/<path:filename>')
def get_alert_image(filename):
    """获取告警图片"""
    try:
        return send_from_directory(current_app.config['ALERT_FOLDER'], filename)
    except Exception as e:
        current_app.logger.error(f"Error getting alert image: {str(e)}")
        return jsonify({'error': str(e)}), 404
