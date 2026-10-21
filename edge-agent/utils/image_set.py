"""把平台上的一张静图重复送给算法，接口与 RtspCapture 对齐。

grab 按约 15fps 节流。调用方如果空转 grab，这里不能立刻返回，否则会占满一个核。
"""
import logging
import os
import threading
import time

import requests
import yaml

logger = logging.getLogger('utils.image_set')

IMAGE_SET_PREFIX = 'image-set:'
_api_base = None


def platform_api_base():
    global _api_base
    if _api_base:
        return _api_base
    found = None
    for path in _config_candidates():
        if path and os.path.isfile(path):
            found = path
            break
    if not found:
        raise ConnectionError('找不到边缘 config.yaml，无法请求图片测试流')
    with open(found, encoding='utf-8') as handle:
        cfg = yaml.safe_load(handle) or {}
    base = str(((cfg.get('platform') or {}).get('api_base_url') or '')).strip().rstrip('/')
    if not base:
        raise ConnectionError(f'{found} 未配置 platform.api_base_url')
    _api_base = base
    return base


def _config_candidates():
    env = os.environ.get('SJIC_EDGE_CONFIG')
    if env:
        yield env
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.yaml'))
    yield here
    yield os.path.abspath('config.yaml')


def open_image_set_capture(url):
    return ImageSetCapture(url).start()


class ImageSetCapture:
    def __init__(self, url):
        raw = str(url or '').strip()
        if not raw.startswith(IMAGE_SET_PREFIX) or not raw[len(IMAGE_SET_PREFIX):].strip():
            raise ValueError(f'invalid image-set url: {url}')
        self._url = raw
        self._set_id = raw[len(IMAGE_SET_PREFIX):].strip()
        self._lock = threading.Lock()
        self._frame = None
        self._opened = False
        self._current_name = None
        self._last_error = ''
        self._last_poll = 0.0
        self._fail_log_t = 0.0
        self._next_grab = 0.0
        self._poll_interval = 1.0
        self._frame_interval = 1.0 / 15.0

    def start(self):
        self._opened = True
        self._maybe_refresh(force=True)
        with self._lock:
            ready = self._frame is not None
        if not ready:
            self._opened = False
            detail = self._last_error or '没有可用图片'
            raise ConnectionError(f'图片测试流 {self._url} 打开失败: {detail}')
        logger.info('image-set ready %s file=%s', self._url, self._current_name)
        return self

    def grab(self):
        if not self._opened:
            return False
        self._maybe_refresh()
        with self._lock:
            ok = self._frame is not None
        if not ok:
            return False
        self._pace()
        return True

    def retrieve(self):
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def read(self):
        if not self.grab():
            return False, None
        return self.retrieve()

    def get(self, prop):
        import cv2
        with self._lock:
            frame = self._frame
        if frame is None:
            return 0
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(frame.shape[0])
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(frame.shape[1])
        if prop == cv2.CAP_PROP_FPS:
            return 15.0
        return 0

    def set(self, prop, value):
        return False

    def isOpened(self):
        with self._lock:
            return self._opened and self._frame is not None

    def release(self):
        with self._lock:
            self._opened = False
            self._frame = None

    def _pace(self):
        interval = self._frame_interval
        if interval <= 0:
            return
        now = time.time()
        delay = self._next_grab - now
        if delay > 0:
            time.sleep(delay)
        self._next_grab = time.time() + interval

    def _log_fail(self, message):
        self._last_error = message
        now = time.time()
        if now - self._fail_log_t < 5:
            return
        self._fail_log_t = now
        logger.warning('image-set %s: %s', self._set_id, message)

    def _maybe_refresh(self, force=False):
        now = time.time()
        if not force and (now - self._last_poll) < self._poll_interval:
            return
        self._last_poll = now
        try:
            base = platform_api_base()
        except Exception as exc:
            self._log_fail(str(exc))
            return
        meta_url = f'{base}/image-sets/{self._set_id}'
        try:
            meta_resp = requests.get(meta_url, timeout=(1.5, 3))
        except Exception as exc:
            self._log_fail(f'清单请求失败: {exc}')
            return
        if meta_resp.status_code != 200:
            self._log_fail(f'清单 HTTP {meta_resp.status_code}')
            return
        try:
            meta = meta_resp.json()
        except Exception as exc:
            self._log_fail(f'清单不是 JSON: {exc}')
            return
        if not isinstance(meta, dict):
            self._log_fail('清单格式无效')
            return
        current = meta.get('current') or None
        if not current:
            if self._frame is None:
                self._log_fail('尚未选择当前图片。请先在「图片测试」页点送入算法')
            return
        with self._lock:
            same = current == self._current_name and self._frame is not None
        if same and not force:
            return
        image_url = f'{base}/image-sets/{self._set_id}/current'
        try:
            image_resp = requests.get(image_url, timeout=(1.5, 15))
        except Exception as exc:
            self._log_fail(f'拉图失败: {exc}')
            return
        if image_resp.status_code != 200:
            self._log_fail(f'拉图 HTTP {image_resp.status_code}')
            return
        frame = _decode_bgr(image_resp.content)
        if frame is None:
            self._log_fail(f'无法解码 {current}')
            return
        with self._lock:
            self._frame = frame
            self._current_name = current
        self._last_error = ''
        logger.info('image-set %s -> %s %sx%s', self._set_id, current, frame.shape[1], frame.shape[0])


def _decode_bgr(raw):
    if not raw:
        return None
    import cv2
    import numpy as np
    arr = np.frombuffer(bytearray(raw), dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None or frame.ndim != 3:
        return None
    if frame.shape[0] < 16 or frame.shape[1] < 16:
        return None
    return frame
