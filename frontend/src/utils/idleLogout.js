/** 连续没有任何操作达到该时长后退出登录。 */
export const IDLE_TIMEOUT_MS = 60 * 60 * 1000;

const ACTIVITY_KEY = 'sjic_last_activity_at';
const WRITE_THROTTLE_MS = 10 * 1000;

let lastWrite = 0;

export function markUserActivity(force = false) {
  const now = Date.now();
  if (!force && now - lastWrite < WRITE_THROTTLE_MS) return;
  lastWrite = now;
  try {
    localStorage.setItem(ACTIVITY_KEY, String(now));
  } catch (e) {
    // 隐私模式等写不进本地存储时，本次会话仍靠内存时间判断
  }
}

export function isUserIdle() {
  let raw = null;
  try {
    raw = localStorage.getItem(ACTIVITY_KEY);
  } catch (e) {
    raw = null;
  }
  if (!raw) return Date.now() - lastWrite >= IDLE_TIMEOUT_MS && lastWrite > 0;
  const ts = Number(raw);
  if (!Number.isFinite(ts) || ts <= 0) return false;
  return Date.now() - ts >= IDLE_TIMEOUT_MS;
}

export function clearLocalSession() {
  lastWrite = 0;
  try {
    localStorage.removeItem(ACTIVITY_KEY);
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('username');
  } catch (e) {
    // 忽略
  }
}
