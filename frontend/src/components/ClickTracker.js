import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import axios from '../utils/axios';

const INTERACTIVE = 'button, a, [role="button"], [role="menuitem"], .MuiTab-root, .MuiMenuItem-root';

function clickLabel(target) {
  if (!target || typeof target.closest !== 'function') return '';
  const el = target.closest(INTERACTIVE);
  if (!el) return '';
  const raw = el.getAttribute('data-track')
    || el.getAttribute('aria-label')
    || el.getAttribute('title')
    || el.innerText
    || '';
  return String(raw).replace(/\s+/g, ' ').trim().slice(0, 80);
}

function ClickTracker() {
  const location = useLocation();
  const queueRef = useRef([]);
  const recentRef = useRef({ key: '', at: 0 });
  const page = location.pathname;

  useEffect(() => {
    const flush = () => {
      if (!queueRef.current.length) return;
      const events = queueRef.current.splice(0, 40);
      axios.post('/api/analytics/clicks', { events }).catch(() => {});
    };

    const onClick = (event) => {
      const label = clickLabel(event.target);
      if (!label) return;
      const key = `${page}|${label}`;
      const now = Date.now();
      if (recentRef.current.key === key && now - recentRef.current.at < 400) return;
      recentRef.current = { key, at: now };
      queueRef.current.push({ page, label });
      if (queueRef.current.length >= 20) flush();
    };

    document.addEventListener('click', onClick, true);
    const timer = window.setInterval(flush, 8000);
    const onHide = () => {
      if (document.visibilityState === 'hidden') flush();
    };
    document.addEventListener('visibilitychange', onHide);
    return () => {
      document.removeEventListener('click', onClick, true);
      document.removeEventListener('visibilitychange', onHide);
      window.clearInterval(timer);
      flush();
    };
  }, [page]);

  return null;
}

export default ClickTracker;
