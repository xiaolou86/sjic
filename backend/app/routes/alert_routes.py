"""
告警管理路由蓝图
"""
import csv
import io
import os
import zipfile
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory, Response, current_app
from sqlalchemy import or_
from app.extensions import db, socketio
from app.models import Alert, Camera
from app.models.alert import ALERT_REVIEW_STATUSES
from app.middleware.auth import token_required, get_token_payload
from app.utils.algorithm_catalog import label_for_alert_type

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


def _alert_to_client(alert):
    data = alert.to_dict()
    data['alert_type_label'] = label_for_alert_type(alert.alert_type)
    return data


EXPORT_LIMIT = 1000


def _alert_query_from_args(source=None):
    """按关键字、时间段、处理状态过滤告警。"""
    source = request.args if source is None else source
    keyword = (source.get('keyword') or source.get('q') or '').strip()
    start = _parse_dt(source.get('start') or source.get('start_time'))
    end = _parse_dt(source.get('end') or source.get('end_time'))
    review_status = (source.get('review_status') or source.get('status') or '').strip()

    query = Alert.query.outerjoin(Camera)

    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(
            Alert.alert_type.ilike(like),
            Alert.message.ilike(like),
            Camera.name.ilike(like),
            Alert.camera_name.ilike(like),
            Alert.review_note.ilike(like),
        ))
    if start is not None:
        query = query.filter(Alert.timestamp >= start)
    if end is not None:
        query = query.filter(Alert.timestamp <= end)
    if review_status and review_status != 'all':
        if review_status == 'pending':
            query = query.filter(or_(
                Alert.review_status == 'pending',
                Alert.review_status.is_(None),
            ))
        else:
            query = query.filter(Alert.review_status == review_status)

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


def _raw_image_filename(filename):
    """带框图 edge_alert_xxx.jpg 对应的原图 edge_alert_xxx_raw.jpg。"""
    base = os.path.basename(filename or '')
    stem, ext = os.path.splitext(base)
    if not stem or stem.endswith('_raw'):
        return None
    return f"{stem}_raw{ext or '.jpg'}"


@alert_bp.route('/api/alerts', methods=['GET'])
@token_required
def get_alerts():
    """
    获取告警记录
    ---
    tags:
      - 告警管理 (Alerts)
    summary: 分页获取告警列表（支持关键字、时间段、处理状态）
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
      - name: review_status
        in: query
        type: string
        description: pending / confirmed / false_positive
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
            'items': [_alert_to_client(alert) for alert in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })

    except Exception as e:
        current_app.logger.error(f"Error getting alerts: {str(e)}")
        return jsonify({'error': str(e)}), 500


@alert_bp.route('/api/alerts/<int:alert_id>/review', methods=['PATCH', 'POST'])
@token_required
def review_alert(alert_id):
    """
    告警确认：属实 / 误报 / 重置为待确认
    """
    try:
        alert = Alert.query.get_or_404(alert_id)
        data = request.json or {}
        status = (data.get('review_status') or data.get('status') or '').strip()
        if status not in ALERT_REVIEW_STATUSES:
            return jsonify({
                'error': '无效的处理状态，请使用 pending / confirmed / false_positive'
            }), 400

        note = data.get('review_note')
        if note is not None:
            note = str(note).strip() or None

        payload = get_token_payload() or {}
        reviewer = payload.get('user') or 'admin'

        alert.review_status = status
        alert.review_note = note
        if status == 'pending':
            alert.reviewed_by = None
            alert.reviewed_at = None
            alert.review_note = note
        else:
            alert.reviewed_by = reviewer
            alert.reviewed_at = datetime.now()

        db.session.commit()
        return jsonify(_alert_to_client(alert))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reviewing alert: {str(e)}")
        return jsonify({'error': str(e)}), 500


def _export_ids():
    """只导出调用方明确勾选的记录，避免把整次查询（含其他页）全部打包。"""
    raw = []
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        raw = data.get('ids') or []
    else:
        text = (request.args.get('ids') or '').strip()
        raw = [part for part in text.split(',') if part.strip()] if text else []
    if isinstance(raw, str):
        raw = [part for part in raw.split(',') if part.strip()]
    ids = []
    seen = set()
    for item in raw:
        try:
            alert_id = int(item)
        except (TypeError, ValueError):
            continue
        if alert_id <= 0 or alert_id in seen:
            continue
        seen.add(alert_id)
        ids.append(alert_id)
        if len(ids) >= 500:
            break
    return ids


@alert_bp.route('/api/alerts/export', methods=['GET', 'POST'])
@token_required
def export_alerts():
    """
    导出告警日志（含带框图和原图）为 ZIP：alerts.csv + images/
    ids：只导出勾选记录。scope=query：导出当前筛选条件下的全部结果（跨页）。
    """
    try:
        body = request.get_json(silent=True) or {}
        export_query = (
            (request.method == 'POST' and body.get('scope') == 'query')
            or request.args.get('scope') == 'query'
        )
        if export_query:
            source = body if request.method == 'POST' else request.args
            query = _alert_query_from_args(source)
            matched = query.count()
            if matched == 0:
                return jsonify({'error': '没有找到可导出的告警记录'}), 404
            if matched > EXPORT_LIMIT:
                return jsonify({
                    'error': f'查询结果共 {matched} 条，超过单次导出上限 {EXPORT_LIMIT} 条，请缩小时间范围后再导出'
                }), 400
            alerts = query.limit(EXPORT_LIMIT).all()
        else:
            ids = _export_ids()
            if not ids:
                return jsonify({'error': '请先勾选要导出的告警记录'}), 400
            alerts = (
                Alert.query.outerjoin(Camera)
                .filter(Alert.id.in_(ids))
                .order_by(Alert.timestamp.desc())
                .all()
            )
            if not alerts:
                return jsonify({'error': '没有找到可导出的告警记录'}), 404
        alert_folder = current_app.config['ALERT_FOLDER']

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow([
                'id', 'timestamp', 'camera_id', 'camera_name',
                'alert_type', 'alert_type_label', 'message', 'confidence',
                'review_status', 'reviewed_by', 'reviewed_at', 'review_note',
                'image_file', 'raw_image_file'
            ])

            for alert in alerts:
                filename = _image_filename(alert)
                archived_name = ''
                raw_archived_name = ''
                if filename:
                    src = os.path.join(alert_folder, os.path.basename(filename))
                    if os.path.isfile(src):
                        archived_name = f'{alert.id}_{os.path.basename(filename)}'
                        zf.write(src, arcname=f'images/{archived_name}')
                    raw_name = _raw_image_filename(filename)
                    raw_src = os.path.join(alert_folder, raw_name) if raw_name else ''
                    if raw_src and os.path.isfile(raw_src):
                        raw_archived_name = f'{alert.id}_{raw_name}'
                        zf.write(raw_src, arcname=f'images/{raw_archived_name}')

                camera_name = alert.camera.name if alert.camera else (alert.camera_name or '')
                writer.writerow([
                    alert.id,
                    alert.timestamp.isoformat() if alert.timestamp else '',
                    alert.camera_id,
                    camera_name,
                    alert.alert_type or '',
                    label_for_alert_type(alert.alert_type),
                    alert.message or '',
                    alert.confidence if alert.confidence is not None else '',
                    alert.review_status or 'pending',
                    alert.reviewed_by or '',
                    alert.reviewed_at.isoformat() if alert.reviewed_at else '',
                    alert.review_note or '',
                    archived_name,
                    raw_archived_name,
                ])

            zf.writestr('alerts.csv', csv_buf.getvalue().encode('utf-8-sig'))

        payload = buf.getvalue()
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'alerts_export_{stamp}.zip'
        return Response(
            payload,
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(payload)),
            },
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
        camera_name=camera.name,
        alert_type=data['alert_type'],
        confidence=data.get('confidence'),
        image_url=data.get('image_url'),
        message=data.get('message'),
        review_status='pending',
    )

    db.session.add(alert)
    db.session.commit()

    socketio.emit('new_alert', _alert_to_client(alert))

    return jsonify(_alert_to_client(alert)), 201


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
        base = os.path.basename(filename)
        stem, _ext = os.path.splitext(base)
        if stem.endswith('_raw'):
            return jsonify({'error': 'Image not found'}), 404
        return send_from_directory(current_app.config['ALERT_FOLDER'], filename)
    except Exception as e:
        current_app.logger.error(f"Error getting alert image: {str(e)}")
        return jsonify({'error': str(e)}), 404
