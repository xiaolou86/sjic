"""界面点击埋点。写入对已登录用户开放，查询仅厂商管理员。"""
import re
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.extensions import db
from app.middleware.auth import get_token_payload, role_required, token_required
from app.models.ui_click import UiClickEvent

analytics_bp = Blueprint('analytics', __name__)

_PAGE_RE = re.compile(r'^/[a-zA-Z0-9/_-]{0,119}$')
_MAX_BATCH = 40


def _clean_label(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:120]


@analytics_bp.route('/api/analytics/clicks', methods=['POST'])
@token_required
def record_clicks():
    payload = get_token_payload() or {}
    body = request.get_json(silent=True) or {}
    events = body.get('events') if isinstance(body, dict) else None
    if not isinstance(events, list) or not events:
        return jsonify({'saved': 0})

    rows = []
    for event in events[:_MAX_BATCH]:
        if not isinstance(event, dict):
            continue
        page = str(event.get('page') or '')
        label = _clean_label(event.get('label'))
        if not label or not _PAGE_RE.match(page):
            continue
        rows.append(UiClickEvent(
            username=(payload.get('user') or '')[:64],
            role=(payload.get('role') or '')[:20],
            page=page[:120],
            label=label,
        ))

    if rows:
        db.session.add_all(rows)
        db.session.commit()
    return jsonify({'saved': len(rows)})


@analytics_bp.route('/api/analytics/hotspots', methods=['GET'])
@role_required('vendor')
def click_hotspots():
    days = request.args.get('days', 7, type=int) or 7
    days = min(max(days, 1), 90)
    page_filter = (request.args.get('page') or '').strip()
    since = datetime.now() - timedelta(days=days)

    query = UiClickEvent.query.filter(UiClickEvent.created_at >= since)
    if page_filter:
        query = query.filter(UiClickEvent.page == page_filter)

    total = query.count()
    grouped = db.session.query(
        UiClickEvent.page,
        UiClickEvent.label,
        func.count(UiClickEvent.id),
        func.count(func.distinct(UiClickEvent.username)),
        func.max(UiClickEvent.created_at),
    ).filter(UiClickEvent.created_at >= since)
    if page_filter:
        grouped = grouped.filter(UiClickEvent.page == page_filter)
    rows = (
        grouped
        .group_by(UiClickEvent.page, UiClickEvent.label)
        .order_by(func.count(UiClickEvent.id).desc())
        .limit(80)
        .all()
    )

    pages = [
        item[0] for item in
        db.session.query(UiClickEvent.page)
        .filter(UiClickEvent.created_at >= since)
        .distinct()
        .order_by(UiClickEvent.page.asc())
        .all()
    ]

    return jsonify({
        'days': days,
        'total_clicks': total,
        'pages': pages,
        'items': [
            {
                'page': page,
                'label': label,
                'clicks': clicks,
                'users': users,
                'last_at': last_at.isoformat() if last_at else None,
            }
            for page, label, clicks, users, last_at in rows
        ],
    })
