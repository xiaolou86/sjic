import hashlib
import hmac
import json
import os
import platform
import subprocess
import uuid
from datetime import datetime, timezone

import yaml


class LicenseService:
    """License validation and quota checks for backend capabilities.

    Fresh install has no license: login works, business APIs are blocked until
    a signed license (trial or official) is imported and matches this machine.
    """

    TRIAL_DAYS = 30
    DEFAULT_TRIAL_MAX_CAMERAS = 4
    # Licenses are issued by license-server/signer.py; keep the canonical payload in sync.
    SIGN_FIELDS = (
        'edition',
        'machine_code',
        'max_cameras',
        'expires_at',
        'allowed_algorithms',
        'issued_at',
        'customer_id',
    )

    def __init__(self):
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.instance_dir = os.path.join(self.base_dir, 'instance')
        # Prefer instance/ (volume-mounted in Docker); fall back to legacy backend/license.json
        self.license_path = os.path.join(self.instance_dir, 'license.json')
        self.legacy_license_path = os.path.join(self.base_dir, 'license.json')
        self.config_path = os.path.join(self.base_dir, 'config.yaml')
        os.makedirs(self.instance_dir, exist_ok=True)

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _signing_key(self):
        cfg = self._load_config()
        key = (
            os.environ.get('LICENSE_SIGNING_KEY')
            or ((cfg.get('license') or {}).get('signing_key'))
            or 'sjic-default-license-signing-key'
        )
        return str(key).encode('utf-8')

    @staticmethod
    def _read_text(path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return (f.read() or '').strip()
        except Exception:
            return ''

    @staticmethod
    def _run_cmd(args):
        try:
            out = subprocess.check_output(
                args,
                stderr=subprocess.DEVNULL,
                timeout=3,
                universal_newlines=True,
            )
            return (out or '').strip()
        except Exception:
            return ''

    @staticmethod
    def _running_in_container():
        """True inside Docker/Podman/etc. where NIC MAC is ephemeral across recreate."""
        if os.environ.get('SJIC_IN_CONTAINER', '').strip().lower() in ('1', 'true', 'yes'):
            return True
        if os.path.exists('/.dockerenv'):
            return True
        try:
            with open('/proc/1/cgroup', 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            if 'docker' in text or 'containerd' in text or 'kubepods' in text or '/libpod/' in text:
                return True
        except Exception:
            pass
        return False

    def _windows_machine_uuid(self):
        if platform.system().lower() != 'windows':
            return ''
        raw = self._run_cmd([
            'powershell',
            '-NoProfile',
            '-Command',
            '(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID',
        ])
        if raw:
            return raw.splitlines()[-1].strip()
        raw = self._run_cmd(['wmic', 'csproduct', 'get', 'uuid'])
        for line in raw.splitlines():
            line = line.strip()
            if line and line.lower() != 'uuid':
                return line
        return ''

    def _resolve_machine_id(self):
        """Prefer host-provided machine-id so container rebuild does not change it."""
        for candidate in (
            os.environ.get('HOST_MACHINE_ID'),
            self._read_text('/host/etc/machine-id'),
            self._read_text('/etc/machine-id'),
            self._read_text('/var/lib/dbus/machine-id'),
        ):
            text = str(candidate or '').strip()
            if text:
                return text
        return ''

    def collect_machine_factors(self, *, include_mac=None):
        """Collect host identifiers that typically differ across cloned VMs.

        Docker/container NIC MAC changes on every recreate/`docker compose --build`,
        so mac_node is omitted in containers by default (include_mac=False).
        """
        if include_mac is None:
            include_mac = not self._running_in_container()

        factors = {
            'system': platform.system() or '',
            'release': platform.release() or '',
            'machine': platform.machine() or '',
            'machine_id': self._resolve_machine_id(),
            'product_uuid': self._read_text('/sys/class/dmi/id/product_uuid'),
            'board_serial': self._read_text('/sys/class/dmi/id/board_serial'),
            'product_serial': self._read_text('/sys/class/dmi/id/product_serial'),
            'windows_uuid': self._windows_machine_uuid(),
        }
        if include_mac:
            factors['mac_node'] = str(uuid.getnode())

        # Drop empty / placeholder DMI values
        cleaned = {}
        for key, value in factors.items():
            text = str(value or '').strip()
            if not text:
                continue
            if text.lower() in ('none', 'not specified', 'to be filled by o.e.m.', 'default string'):
                continue
            cleaned[key] = text
        return cleaned

    @staticmethod
    def _hash_factors(factors):
        raw = '|'.join(f'{k}={factors[k]}' for k in sorted(factors.keys()))
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get_machine_code(self):
        """Stable fingerprint for license issuance (ignores ephemeral container MAC)."""
        return self._hash_factors(self.collect_machine_factors())

    def iter_machine_codes(self):
        """Accept stable and legacy fingerprints so upgrades do not break current hosts."""
        seen = set()
        for include_mac in (False, True):
            code = self._hash_factors(self.collect_machine_factors(include_mac=include_mac))
            if code not in seen:
                seen.add(code)
                yield code

    def _machine_code_matches(self, licensed_machine_code):
        licensed = str(licensed_machine_code or '').strip()
        if not licensed:
            return False
        return licensed in set(self.iter_machine_codes())

    @staticmethod
    def _format_date(value):
        """Normalize to YYYY-MM-DD for license file fields.

        Accepts: YYYY-MM-DD, YYYYMMDD, or legacy ISO datetime.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).date().isoformat()
        text = str(value).strip()
        if not text:
            return None

        # YYYY-MM-DD
        if len(text) >= 10 and text[4] == '-' and text[7] == '-':
            candidate = text[:10]
            try:
                datetime.strptime(candidate, '%Y-%m-%d')
                return candidate
            except ValueError:
                return None

        # YYYYMMDD
        if len(text) == 8 and text.isdigit():
            try:
                dt = datetime.strptime(text, '%Y%m%d')
                return dt.date().isoformat()
            except ValueError:
                return None

        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()

    def _parse_license_date(self, value, *, end_of_day=False):
        """Parse YYYY-MM-DD (or legacy ISO datetime) to UTC datetime for comparison."""
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        text = str(value).strip()
        date_text = self._format_date(text)
        if not date_text:
            return None
        try:
            year, month, day = (int(x) for x in date_text.split('-'))
        except Exception:
            return None

        if end_of_day:
            # expires_at is inclusive through that calendar day (UTC)
            dt = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        else:
            dt = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        return dt

    def _canonical_payload(self, data):
        payload = {}
        for field in self.SIGN_FIELDS:
            value = data.get(field)
            if field == 'allowed_algorithms':
                algos = value or []
                if not isinstance(algos, list):
                    algos = []
                payload[field] = sorted(str(x) for x in algos)
            elif field == 'max_cameras':
                payload[field] = int(value or 0)
            elif field == 'edition':
                payload[field] = str(value or '').strip().lower()
            elif field in ('expires_at', 'issued_at'):
                payload[field] = self._format_date(value) or ''
            else:
                payload[field] = '' if value is None else str(value).strip()
        return payload

    def sign_license(self, data):
        payload = self._canonical_payload(data)
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        return hmac.new(self._signing_key(), body.encode('utf-8'), hashlib.sha256).hexdigest()

    def verify_signature(self, data):
        expected = str(data.get('signature') or '').strip().lower()
        if not expected:
            return False
        actual = self.sign_license(data)
        return hmac.compare_digest(actual, expected)

    def _resolve_license_path(self):
        if os.path.exists(self.license_path):
            return self.license_path
        if os.path.exists(self.legacy_license_path):
            return self.legacy_license_path
        return self.license_path

    def _load_license_file(self):
        path = self._resolve_license_path()
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_license(self, data):
        os.makedirs(self.instance_dir, exist_ok=True)
        with open(self.license_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return self.license_path

    def import_license(self, raw):
        """Validate and persist an imported license. Returns (ok, reason, status)."""
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except Exception:
                return False, 'invalid_json', self.get_status()
        elif isinstance(raw, dict):
            data = raw
        else:
            return False, 'invalid_json', self.get_status()

        if not isinstance(data, dict):
            return False, 'invalid_json', self.get_status()

        if not self.verify_signature(data):
            return False, 'invalid_signature', self.get_status()

        edition = str(data.get('edition', '')).strip().lower()
        if edition not in ('trial', 'official'):
            return False, 'invalid_edition', self.get_status()

        licensed_machine = str(data.get('machine_code', '')).strip()
        if not self._machine_code_matches(licensed_machine):
            return False, 'machine_mismatch', self.get_status()

        expires_at = self._parse_license_date(data.get('expires_at'), end_of_day=True)
        if not expires_at:
            return False, 'invalid_expires_at', self.get_status()

        now = datetime.now(timezone.utc)
        if now > expires_at:
            return False, 'license_expired', self.get_status()

        try:
            max_cameras = int(data.get('max_cameras', 0) or 0)
        except Exception:
            return False, 'invalid_max_cameras', self.get_status()

        if max_cameras < 0:
            return False, 'invalid_max_cameras', self.get_status()

        # Persist original signed payload (do not reformat signed fields)
        self.save_license(data)
        return True, '', self.get_status()

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
            return {
                'valid': False,
                'edition': None,
                'reason': 'license_required',
                'machine_code': machine_code,
                'max_cameras': 0,
                'allowed_algorithms': [],
                'expires_at': None,
                'issued_at': None,
                'customer_id': '',
                'trial_max_cameras': trial_max_cameras,
                'trial_days': self.TRIAL_DAYS,
            }

        edition = str(license_data.get('edition', 'official')).strip().lower()
        expires_at = self._parse_license_date(license_data.get('expires_at'), end_of_day=True)
        issued_at_date = self._format_date(license_data.get('issued_at'))
        expires_at_date = self._format_date(license_data.get('expires_at'))
        licensed_machine_code = str(license_data.get('machine_code', '')).strip()
        max_cameras = int(license_data.get('max_cameras', 0) or 0)
        allowed_algorithms = license_data.get('allowed_algorithms') or []
        customer_id = license_data.get('customer_id') or ''

        base = {
            'edition': edition,
            'machine_code': machine_code,
            'max_cameras': max_cameras,
            'allowed_algorithms': allowed_algorithms,
            'expires_at': expires_at_date,
            'issued_at': issued_at_date,
            'customer_id': customer_id,
            'trial_max_cameras': trial_max_cameras,
            'trial_days': self.TRIAL_DAYS,
        }

        if not self.verify_signature(license_data):
            return {**base, 'valid': False, 'reason': 'invalid_signature'}

        if licensed_machine_code and not self._machine_code_matches(licensed_machine_code):
            return {**base, 'valid': False, 'reason': 'machine_mismatch'}

        if expires_at and now > expires_at:
            return {**base, 'valid': False, 'reason': 'license_expired'}

        return {**base, 'valid': True, 'reason': ''}

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
