#!/usr/bin/env python3
"""Issue a license from the command line; the record is saved like the web page does.

  python generate_license.py --machine-code <code> --edition trial --max-cameras 4 --out license.json
  python generate_license.py --machine-code <code> --edition official --max-cameras 32 \\
      --expires-at 2027-12-31 --customer-id acme --out license.json

Without --out the license JSON is printed to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import signer
from store import Store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description='Issue SJIC license.json')
    parser.add_argument('--machine-code', required=True, help='machine_code from platform 授权管理 page')
    parser.add_argument('--edition', choices=signer.EDITIONS, required=True)
    parser.add_argument('--max-cameras', type=int, required=True, help='0 means unlimited')
    parser.add_argument('--expires-at', default=None, help='Required for official (YYYY-MM-DD or YYYYMMDD)')
    parser.add_argument('--customer-id', default='')
    parser.add_argument('--algorithms', default='', help='Comma-separated algorithm types; empty = all')
    parser.add_argument('--note', default='', help='Stored locally, not written into the license')
    parser.add_argument('--out', default=None, help='Output file; default prints to stdout')
    parser.add_argument('--signing-key', default=None, help='Default: env LICENSE_SIGNING_KEY')
    parser.add_argument('--db', default=None, help='Default: env LICENSE_DB_PATH or data/licenses.db')
    args = parser.parse_args()

    try:
        data = signer.build_license(
            key=args.signing_key or os.environ.get('LICENSE_SIGNING_KEY', ''),
            edition=args.edition,
            machine_code=args.machine_code,
            max_cameras=args.max_cameras,
            expires_at=args.expires_at,
            allowed_algorithms=args.algorithms.split(','),
            customer_id=args.customer_id,
        )
    except ValueError as exc:
        parser.error(str(exc))

    db_path = args.db or os.environ.get('LICENSE_DB_PATH') or os.path.join(BASE_DIR, 'data', 'licenses.db')
    license_id = Store(db_path).add(data, note=args.note)

    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'#{license_id} wrote {os.path.abspath(args.out)}', file=sys.stderr)
    else:
        print(text)
        print(f'#{license_id} saved', file=sys.stderr)


if __name__ == '__main__':
    main()
