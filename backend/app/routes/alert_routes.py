"""
告警管理路由蓝图
"""
import csv
import io
import os
import zipfile
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory, send_file, current_app
from sqlalchemy import or_
from app.extensions import db, socketio
from app.models import Alert, Camera
from app.middleware.auth import token_required

alert_bp = Blueprint('alert', __name__)


def _parse_dt(value):
    """解析查询时间参数，支持 ISO / datetime-local 常见格式。"""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _alert_query_from_args():
    """按关键字（模糊）与时间段过滤告警。"""
    keyword = (request.args.get('keyword') or request.args.get('q') or '').strip()
    start = _parse_dt(request.args.get('start') or request.args.get('start_time'))
    end = _parse_dt(request.args.get('end') or request.args.get('end_time'))

    query = Alert.query.outerjoin(Camera)

    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(
            Alert.alert_type.ilike(like),
            Alert.message.ilike(like),
            Camera.name.ilike(like),
        ))
    if start is not None:
        query = query.filter(Alert.timestamp >= start)
    if end is not None:
        query = query.filter(Alert.timestamp <= end)

    return query.order_by(Alert.timestamp.desc())


def _image_filename(alert):
    """从告警记录解析本地图片文件名。"""
    raw = alert.image_url
    if not raw:
        return None
    if raw.startswith('http'):
        return raw.rsplit('/', 1)[-1] or None
    if raw.startswith('/api/alerts/images/'):
        return raw[len('/api/alerts/images/'):]
    return raw.lstrip('/')


@alert_bp.route('/api/alerts', methods=['GET'])
@token_required
def get_alerts():
    """
    获取告警记录
    ---
    tags:
      - 告警管理 (Alerts)
    summary: 分页获取告警列表（支持关键字与时间段）
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
      - name: keyword
        in: query
        type: string
        description: 关键字（摄像头名/类型/说明模糊匹配）
      - name: start
        in: query
        type: string
        description: 开始时间
      - name: end
        in: query
        type: string
        description: 结束时间
    responses:
      200:
        description: 告警列表和分页信息
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        pagination = _alert_query_from_args().paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        return jsonify({
            'items': [alert.to_dict() for alert in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })

    except Exception as e:
        current_app.logger.error(f"Error getting alerts: {str(e)}")
        return jsonify({'error': str(e)}), 500


@alert_bp.route('/api/alerts/export', methods=['GET'])
@token_required
def export_alerts():
    """
    导出告警日志（含图片）为 ZIP：alerts.csv + images/
    """
    try:
        alerts = _alert_query_from_args().limit(5000).all()
        alert_folder = current_app.config['ALERT_FOLDER']

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow([
                'id', 'timestamp', 'camera_id', 'camera_name',
                'alert_type', 'message', 'confidence', 'image_file'
            ])

            for alert in alerts:
                filename = _image_filename(alert)
                archived_name = ''
                if filename:
                    src = os.path.join(alert_folder, filename)
                    if os.path.isfile(src):
                        # 避免重名覆盖：用 id 前缀
                        archived_name = f'{alert.id}_{os.path.basename(filename)}'
                        zf.write(src, arcname=f'images/{archived_name}')

                camera_name = alert.camera.name if alert.camera else ''
                writer.writerow([
                    alert.id,
                    alert.timestamp.isoformat() if alert.timestamp else '',
                    alert.camera_id,
                    camera_name,
                    alert.alert_type or '',
                    alert.message or '',
                    alert.confidence if alert.confidence is not None else '',
                    archived_name,
                ])

            # utf-8-sig 方便 Excel 打开中文
            zf.writestr('alerts.csv', csv_buf.getvalue().encode('utf-8-sig'))

        buf.seek(0)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            buf,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'alerts_export_{stamp}.zip',
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting alerts: {str(e)}")
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
