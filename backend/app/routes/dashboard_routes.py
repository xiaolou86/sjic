"""
首页概览统计路由
"""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, current_app
from sqlalchemy import func
from app.extensions import db
from app.models.camera import Camera
from app.models.detection_model import DetectionModel
from app.models.edge_node import EdgeNode
from app.models.task import Task
from app.models.alert import Alert
from app.middleware.auth import token_required
from app.utils.algorithm_catalog import detection_scene_count, label_for_alert_type

dashboard_bp = Blueprint('dashboard', __name__)


def _day_start(dt=None):
    dt = dt or datetime.now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


@dashboard_bp.route('/api/dashboard/summary', methods=['GET'])
@token_required
def dashboard_summary():
    """
    首页概述：资源数量、运行时长、分时段告警、场景统计、近期告警
    """
    try:
        camera_count = Camera.query.count()
        model_count = DetectionModel.query.count()
        scene_count = detection_scene_count()
        node_count = EdgeNode.query.count()
        online_node_count = EdgeNode.query.filter_by(status='online').count()
        task_count = Task.query.count()
        running_task_count = Task.query.filter(
            db.or_(
                Task.run_status == 'running',
                Task.status == 'running',
            )
        ).count()

        today_start = _day_start()
        week_start = today_start - timedelta(days=6)

        alerts_today = Alert.query.filter(Alert.timestamp >= today_start).count()
        alerts_7d = Alert.query.filter(Alert.timestamp >= week_start).count()
        alerts_pending = Alert.query.filter(
            db.or_(Alert.review_status == 'pending', Alert.review_status.is_(None))
        ).count()
        alerts_confirmed_7d = Alert.query.filter(
            Alert.timestamp >= week_start,
            Alert.review_status == 'confirmed',
        ).count()
        alerts_false_7d = Alert.query.filter(
            Alert.timestamp >= week_start,
            Alert.review_status == 'false_positive',
        ).count()

        today_by_type = dict(
            db.session.query(Alert.alert_type, func.count(Alert.id))
            .filter(Alert.timestamp >= today_start)
            .group_by(Alert.alert_type)
            .all()
        )
        week_rows = (
            db.session.query(Alert.alert_type, func.count(Alert.id))
            .filter(Alert.timestamp >= week_start)
            .group_by(Alert.alert_type)
            .order_by(func.count(Alert.id).desc())
            .all()
        )
        by_scenario = [
            {
                'alert_type': alert_type,
                'label': label_for_alert_type(alert_type),
                'count_today': int(today_by_type.get(alert_type, 0)),
                'count_7d': int(count_7d),
            }
            for alert_type, count_7d in week_rows
        ]
        # 仅今日有、近7天聚合未覆盖的（理论上不会，兜底）
        for alert_type, count_today in today_by_type.items():
            if not any(s['alert_type'] == alert_type for s in by_scenario):
                by_scenario.append({
                    'alert_type': alert_type,
                    'label': label_for_alert_type(alert_type),
                    'count_today': int(count_today),
                    'count_7d': int(count_today),
                })

        started_at = current_app.config.get('APP_STARTED_AT') or datetime.now()
        uptime_seconds = max(0, int((datetime.now() - started_at).total_seconds()))

        recent_alerts = (
            Alert.query.order_by(Alert.timestamp.desc())
            .limit(20)
            .all()
        )
        latest_alert = recent_alerts[0].to_dict() if recent_alerts else None
        if latest_alert:
            latest_alert['alert_type_label'] = label_for_alert_type(
                latest_alert.get('alert_type')
            )

        recent_payload = []
        for a in recent_alerts:
            item = a.to_dict()
            item['alert_type_label'] = label_for_alert_type(a.alert_type)
            recent_payload.append(item)

        return jsonify({
            'counts': {
                'cameras': camera_count,
                'models': model_count,
                'algorithm_scenes': scene_count,
                'nodes': node_count,
                'nodes_online': online_node_count,
                'tasks': task_count,
                'tasks_running': running_task_count,
                'alerts_today': alerts_today,
                'alerts_7d': alerts_7d,
                'alerts_pending': alerts_pending,
                'alerts_confirmed_7d': alerts_confirmed_7d,
                'alerts_false_7d': alerts_false_7d,
                # 兼容旧前端：alerts 表示待确认数（更贴近运营关注点）
                'alerts': alerts_pending,
            },
            'uptime': {
                'started_at': started_at.isoformat(),
                'seconds': uptime_seconds,
            },
            'by_scenario': by_scenario,
            'recent_alerts': recent_payload,
            'latest_alert': latest_alert,
        })
    except Exception as e:
        current_app.logger.error(f"Error building dashboard summary: {str(e)}")
        return jsonify({'error': str(e)}), 500
