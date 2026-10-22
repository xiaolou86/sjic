"""摄像头遮挡：只统计画面最外一圈格子是否失去纹理。"""
import numpy as np

# 外圈格子在模糊后的标准差低于此值，视为这块没有画面内容。
# 近黑和发灰的遮挡都会落在这里，不要求像素为 0。
DEFAULT_STD_MAX = 8.0
# 格子边长。只统计最外一圈，遮挡从画面边缘进来时先碰到这一圈。
DEFAULT_BLOCK = 32
# 外圈里失效格子的占比。大约一条长边被挡住就会超过。
DEFAULT_COVER_RATIO = 0.25
DEFAULT_HOLD_SECONDS = 3.0


def _to_gray(frame):
    image = np.asarray(frame)
    if image.ndim == 2:
        return image.astype(np.float32, copy=False)
    if image.ndim == 3 and image.shape[2] >= 3:
        blue = image[:, :, 0].astype(np.float32)
        green = image[:, :, 1].astype(np.float32)
        red = image[:, :, 2].astype(np.float32)
        return 0.114 * blue + 0.587 * green + 0.299 * red
    return None


def _box_blur(gray, radius=2):
    """5×5 方框模糊，压掉传感器噪点，景物边缘还在。"""
    k = radius * 2 + 1
    height, width = gray.shape[:2]
    horizontal = np.pad(gray, ((0, 0), (radius, radius)), mode='edge')
    acc = np.zeros((height, width), dtype=np.float32)
    for offset in range(k):
        acc += horizontal[:, offset:offset + width]
    acc /= k
    vertical = np.pad(acc, ((radius, radius), (0, 0)), mode='edge')
    out = np.zeros((height, width), dtype=np.float32)
    for offset in range(k):
        out += vertical[offset:offset + height, :]
    return out / k


def is_occlusion_spec(spec):
    if not isinstance(spec, dict):
        return False
    return spec.get('type') == 'camera_occlusion' or spec.get('scene_preset_id') == 'camera_occlusion'


def update_occlusion(spec, frame, now, state, cooldown_sec):
    """外圈发平并持续足够久则返回告警文案。state 就地更新。"""
    try:
        cover_ratio = float(spec.get('cover_ratio', DEFAULT_COVER_RATIO))
    except (TypeError, ValueError):
        cover_ratio = DEFAULT_COVER_RATIO
    try:
        std_max = float(spec.get('std_max', DEFAULT_STD_MAX))
    except (TypeError, ValueError):
        std_max = DEFAULT_STD_MAX
    try:
        block = int(spec.get('block', DEFAULT_BLOCK))
    except (TypeError, ValueError):
        block = DEFAULT_BLOCK
    try:
        hold = float(spec.get('seconds', DEFAULT_HOLD_SECONDS))
    except (TypeError, ValueError):
        hold = DEFAULT_HOLD_SECONDS
    try:
        cooldown = float(cooldown_sec or 0)
    except (TypeError, ValueError):
        cooldown = 0.0

    ratio = ring_occlusion_ratio(frame, block=block, std_max=std_max)
    state['ratio'] = ratio
    if ratio < cover_ratio:
        state['since'] = None
        return None
    since = state.get('since')
    if since is None:
        state['since'] = now
        return None
    elapsed = (now - since).total_seconds()
    if elapsed < hold:
        return None
    last = state.get('last_alert')
    if last is not None and (now - last).total_seconds() < cooldown:
        return None
    state['last_alert'] = now
    state['since'] = now
    return f"摄像头遮挡：外圈 {ratio:.0%} 持续 {elapsed:.1f}s"


def occlusion_preview(specs, states, now=None):
    """最新一帧外圈发平占比，给预览用。没算过的场景不出现。"""
    best = None
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        bid = spec.get('id') or spec.get('type') or 'camera_occlusion'
        state = (states or {}).get(bid) or {}
        ratio = state.get('ratio')
        if ratio is None:
            continue
        try:
            cover = float(spec.get('cover_ratio', DEFAULT_COVER_RATIO))
        except (TypeError, ValueError):
            cover = DEFAULT_COVER_RATIO
        try:
            seconds = float(spec.get('seconds', DEFAULT_HOLD_SECONDS))
        except (TypeError, ValueError):
            seconds = DEFAULT_HOLD_SECONDS
        held = None
        since = state.get('since')
        if now is not None and since is not None:
            try:
                held = round((now - since).total_seconds(), 1)
            except (TypeError, ValueError, AttributeError):
                held = None
        item = {
            'name': spec.get('name') or '摄像头遮挡',
            'ratio': round(float(ratio), 4),
            'cover_ratio': cover,
            'seconds': seconds,
            'hit': float(ratio) >= cover,
            'held': held,
        }
        if best is None or item['ratio'] > best['ratio']:
            best = item
    return best


def ring_occlusion_ratio(frame, block=DEFAULT_BLOCK, std_max=DEFAULT_STD_MAX):
    """最外一圈格子中，模糊后仍然发平的占比。中心格子不参与。"""
    if frame is None or getattr(frame, "size", 0) == 0:
        return 0.0
    gray = _to_gray(frame)
    if gray is None:
        return 0.0
    gray = _box_blur(gray)
    height, width = gray.shape[:2]
    block = max(int(block), 8)
    rows = max(1, height // block)
    cols = max(1, width // block)
    ys = [int(round(i * height / rows)) for i in range(rows + 1)]
    xs = [int(round(i * width / cols)) for i in range(cols + 1)]

    dead = 0
    total = 0
    for row in range(rows):
        for col in range(cols):
            on_ring = rows == 1 or cols == 1 or row in (0, rows - 1) or col in (0, cols - 1)
            if not on_ring:
                continue
            patch = gray[ys[row]:ys[row + 1], xs[col]:xs[col + 1]]
            if patch.size == 0:
                continue
            total += 1
            if float(patch.std()) < float(std_max):
                dead += 1
    if total == 0:
        return 0.0
    return dead / total
