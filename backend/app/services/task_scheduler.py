"""
定时任务调度：对设置了 schedule_start/schedule_end 的任务，
按每日时间窗自动启停（场景级时段由边缘侧门控，不在此处理）。
"""
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler_started = False
_lock = threading.Lock()


def _parse_hhmm(value):
    if not value:
        return None
    text = str(value).strip()
    parts = text.split(':')
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def in_daily_window(now, start_hhmm, end_hhmm):
    start = _parse_hhmm(start_hhmm)
    end = _parse_hhmm(end_hhmm)
    if start is None or end is None:
        return False
    cur = now.hour * 60 + now.minute
    if start == end:
        return True
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def _is_running_status(status):
    s = (status or '').lower()
    return s in ('running', 'syncing', 'starting', 'waiting')


def tick_once(app):
    """扫描一次定时任务并启停。"""
    from app.models import Task
    from app.services.detector import DetectorService

    detector = DetectorService()
    now = datetime.now()
    with app.app_context():
        tasks = Task.query.filter(
            Task.schedule_start.isnot(None),
            Task.schedule_end.isnot(None),
        ).all()
        for task in tasks:
            if not task.has_schedule():
                continue
            if task.schedule_paused:
                continue
            active = in_daily_window(now, task.schedule_start, task.schedule_end)
            running = _is_running_status(task.status) or _is_running_status(task.run_status)
            if active and not running:
                logger.info(
                    "Schedule start task %s (%s–%s)",
                    task.id, task.schedule_start, task.schedule_end,
                )
                try:
                    detector.start_detection(task.id)
                except Exception as e:
                    logger.warning("Schedule start task %s failed: %s", task.id, e)
            elif (not active) and running:
                logger.info(
                    "Schedule stop task %s (outside %s–%s)",
                    task.id, task.schedule_start, task.schedule_end,
                )
                try:
                    detector.stop_detection(task.id, pause_schedule=False)
                except Exception as e:
                    logger.warning("Schedule stop task %s failed: %s", task.id, e)


def _loop(app, interval_sec=30):
    while True:
        try:
            tick_once(app)
        except Exception as e:
            logger.exception("Task schedule tick failed: %s", e)
        time.sleep(interval_sec)


def start_task_scheduler(app, interval_sec=30):
    from app.utils.serve_process import should_start_background_services
    if not should_start_background_services():
        logger.info("Skipping task scheduler in Werkzeug reloader parent process.")
        return

    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    t = threading.Thread(
        target=_loop,
        args=(app, interval_sec),
        name='task-schedule',
        daemon=True,
    )
    t.start()
    logger.info("Task schedule worker started (interval=%ss)", interval_sec)
