import hashlib
import json
import os
import platform
import socket
import uuid
from datetime import datetime, timedelta, timezone
import yaml


class LicenseService:
    """License validation and quota checks for backend capabilities."""

    TRIAL_DAYS = 30
    DEFAULT_TRIAL_MAX_CAMERAS = 4

    def __init__(self):
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.instance_dir = os.path.join(self.base_dir, 'instance')
        self.license_path = os.path.join(self.base_dir, 'license.json')
        self.config_path = os.path.join(self.base_dir, 'config.yaml')
        self.trial_state_path = os.path.join(self.instance_dir, 'license_trial_state.json')
        os.makedirs(self.instance_dir, exist_ok=True)

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def get_machine_code(self):
        """Generate a stable backend machine fingerprint hash."""
        raw = "|".join([
            socket.gethostname() or '',
            platform.system() or '',
            platform.release() or '',
            str(uuid.getnode()),
        ])
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def _parse_iso_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if text.endswith('Z'):
                text = text[:-1] + '+00:00'
            dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _load_license_file(self):
        if not os.path.exists(self.license_path):
            return None
        with open(self.license_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_trial_start(self):
        now = datetime.now(timezone.utc)
        if os.path.exists(self.trial_state_path):
            with open(self.trial_state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            start = self._parse_iso_datetime(data.get('trial_start_at'))
            if start:
                return start

        with open(self.trial_state_path, 'w', encoding='utf-8') as f:
            json.dump({'trial_start_at': now.isoformat()}, f, ensure_ascii=False, indent=2)
        return now

    def get_status(self):
        now = datetime.now(timezone.utc)
        machine_code = self.get_machine_code()
        license_data = self._load_license_file()
        cfg = self._load_config()
        trial_max_cameras = int(
            ((cfg.get('license') or {}).get('trial_max_cameras'))
            or self.DEFAULT_TRIAL_MAX_CAMERAS
        )

        if not license_data:
            trial_start = self._load_trial_start()
            expires_at = trial_start + timedelta(days=self.TRIAL_DAYS)
            valid = now <= expires_at
            return {
                'valid': valid,
                'edition': 'trial',
                'reason': '' if valid else 'trial_expired',
                'machine_code': machine_code,
                'max_cameras': trial_max_cameras,
                'allowed_algorithms': [],
                'expires_at': expires_at.isoformat(),
                'trial_start_at': trial_start.isoformat(),
            }

        edition = str(license_data.get('edition', 'official')).strip().lower()
        expires_at = self._parse_iso_datetime(license_data.get('expires_at'))
        licensed_machine_code = str(license_data.get('machine_code', '')).strip()
        max_cameras = int(license_data.get('max_cameras', 0) or 0)
        allowed_algorithms = license_data.get('allowed_algorithms') or []

        if licensed_machine_code and licensed_machine_code != machine_code:
            return {
                'valid': False,
                'edition': edition,
                'reason': 'machine_mismatch',
                'machine_code': machine_code,
                'max_cameras': max_cameras,
                'allowed_algorithms': allowed_algorithms,
                'expires_at': expires_at.isoformat() if expires_at else None,
            }

        if expires_at and now > expires_at:
            return {
                'valid': False,
                'edition': edition,
                'reason': 'license_expired',
                'machine_code': machine_code,
                'max_cameras': max_cameras,
                'allowed_algorithms': allowed_algorithms,
                'expires_at': expires_at.isoformat(),
            }

        return {
            'valid': True,
            'edition': edition,
            'reason': '',
            'machine_code': machine_code,
            'max_cameras': max_cameras,
            'allowed_algorithms': allowed_algorithms,
            'expires_at': expires_at.isoformat() if expires_at else None,
        }

    def ensure_valid(self):
        status = self.get_status()
        if not status['valid']:
            reason = status.get('reason') or 'license_invalid'
            return False, reason
        return True, ''

    def is_algorithm_allowed(self, algorithm_type):
        """Return True when the algorithm is permitted by current license."""
        status = self.get_status()
        if not status['valid']:
            return False, status.get('reason') or 'license_invalid'

        allowed = status.get('allowed_algorithms') or []
        if not allowed:
            return True, ''

        if algorithm_type in allowed:
            return True, ''
        return False, 'algorithm_not_licensed'

    def can_add_camera(self, current_count):
        status = self.get_status()
        if not status['valid']:
            return False, status.get('reason') or 'license_invalid', status

        limit = int(status.get('max_cameras', 0) or 0)
        if limit <= 0:
            return True, '', status

        if current_count >= limit:
            return False, 'camera_quota_exceeded', status
        return True, '', status


license_service = LicenseService()