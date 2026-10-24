"""Minimal web page for issuing SJIC licenses and listing issued ones."""
from __future__ import annotations

import hmac
import io
import os

from flask import Flask, Response, abort, redirect, render_template, request, send_file, url_for

import signer
from store import Store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SIGNING_KEY=os.environ.get('LICENSE_SIGNING_KEY', ''),
        DB_PATH=os.environ.get('LICENSE_DB_PATH') or os.path.join(BASE_DIR, 'data', 'licenses.db'),
        ADMIN_USER=os.environ.get('LICENSE_ADMIN_USER', 'admin'),
        ADMIN_PASSWORD=os.environ.get('LICENSE_ADMIN_PASSWORD', ''),
    )
    if config:
        app.config.update(config)
    if not app.config['SIGNING_KEY']:
        raise RuntimeError('LICENSE_SIGNING_KEY is required and must match the platform backend')
    if not app.config['ADMIN_PASSWORD']:
        app.logger.warning('LICENSE_ADMIN_PASSWORD is empty; the page is not password protected')

    store = Store(app.config['DB_PATH'])

    @app.before_request
    def require_basic_auth():
        password = app.config['ADMIN_PASSWORD']
        if not password:
            return None
        auth = request.authorization
        if auth and _same(auth.username, app.config['ADMIN_USER']) and _same(auth.password, password):
            return None
        return Response('需要登录', 401, {'WWW-Authenticate': 'Basic realm="sjic-license", charset="UTF-8"'})

    def render_index(form=None, error='', status=200):
        return render_template(
            'index.html',
            licenses=store.list(),
            form=form or {'edition': 'trial', 'max_cameras': '4'},
            error=error,
            created=request.args.get('created', type=int),
            trial_days=signer.TRIAL_DAYS,
        ), status

    @app.get('/')
    def index():
        return render_index()

    @app.post('/licenses')
    def create_license():
        form = request.form.to_dict()
        raw_algos = form.get('allowed_algorithms', '').replace('，', ',')
        try:
            data = signer.build_license(
                key=app.config['SIGNING_KEY'],
                edition=form.get('edition'),
                machine_code=form.get('machine_code'),
                max_cameras=form.get('max_cameras'),
                expires_at=form.get('expires_at'),
                allowed_algorithms=raw_algos.split(','),
                customer_id=form.get('customer_id'),
            )
        except ValueError as exc:
            return render_index(form=form, error=str(exc), status=400)
        license_id = store.add(data, note=form.get('note'))
        return redirect(url_for('index', created=license_id))

    @app.get('/licenses/<int:license_id>.json')
    def download_license(license_id):
        row = store.get(license_id)
        if not row:
            abort(404)
        return send_file(
            io.BytesIO(row['license_json'].encode('utf-8')),
            mimetype='application/json',
            as_attachment=request.args.get('inline') != '1',
            download_name=f'license-{license_id}.json',
        )

    return app


def _same(a, b):
    return hmac.compare_digest((a or '').encode('utf-8'), (b or '').encode('utf-8'))


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.environ.get('PORT', '38890')))
