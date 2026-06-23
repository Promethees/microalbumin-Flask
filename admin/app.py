"""Easy OKAPI — local admin console (license kill-switch).

A tiny LOCAL-ONLY Flask app the admin runs on their own machine to revoke or
reinstate a customer's license. It never holds any app data: it just forwards
two calls to the production server's shared-secret admin API —

    GET  /api/admin/lookup?email=...     (read a user + their machine seats)
    POST /api/admin/revoke  {email, revoked}

— attaching the X-Admin-Key header. The admin key lives ONLY in this process's
environment (loaded from admin/.env); it is never sent to the browser, so it
can't leak into page source or browser history.

This whole tool lives on the secret `offline` branch and is meant to be run
locally only — do NOT deploy it. See README.md.

Run:
    pip install -r requirements.txt
    cp .env.example .env   # then fill in ADMIN_API_KEY (+ SERVER_URL if needed)
    python app.py          # opens http://127.0.0.1:7800
"""
import os
import webbrowser
import threading

import requests
from flask import Flask, request, jsonify, render_template


def _load_dotenv(path='.env'):
    """Minimal .env loader (avoids a python-dotenv dependency).

    KEY=VALUE per line; blank lines and #-comments ignored; existing env wins.
    """
    if not os.path.isfile(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

SERVER_URL = os.environ.get('SERVER_URL', 'https://www.easyokapi.cbbiotec.vn').rstrip('/')
ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', '')
PORT = int(os.environ.get('ADMIN_UI_PORT', '7800'))

app = Flask(__name__)


def _headers():
    return {'X-Admin-Key': ADMIN_API_KEY}


def _relay(resp):
    """Pass the upstream JSON + status straight through to our browser client."""
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({'status': 'error',
                        'message': f'Non-JSON response from server (HTTP {resp.status_code})'}), 502


@app.route('/')
def index():
    return render_template('admin.html', server_url=SERVER_URL,
                           key_configured=bool(ADMIN_API_KEY))


@app.route('/api/lookup')
def lookup():
    if not ADMIN_API_KEY:
        return jsonify({'status': 'error', 'message': 'ADMIN_API_KEY is not set in admin/.env'}), 503
    email = (request.args.get('email') or '').strip()
    if not email:
        return jsonify({'status': 'error', 'message': 'email is required'}), 400
    try:
        r = requests.get(f'{SERVER_URL}/api/admin/lookup',
                         params={'email': email}, headers=_headers(), timeout=20)
    except requests.RequestException as e:
        return jsonify({'status': 'error', 'message': f'Cannot reach server: {e}'}), 502
    return _relay(r)


@app.route('/api/revoke', methods=['POST'])
def revoke():
    if not ADMIN_API_KEY:
        return jsonify({'status': 'error', 'message': 'ADMIN_API_KEY is not set in admin/.env'}), 503
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    revoked = bool(data.get('revoked', True))
    if not email:
        return jsonify({'status': 'error', 'message': 'email is required'}), 400
    try:
        r = requests.post(f'{SERVER_URL}/api/admin/revoke',
                          json={'email': email, 'revoked': revoked},
                          headers=_headers(), timeout=20)
    except requests.RequestException as e:
        return jsonify({'status': 'error', 'message': f'Cannot reach server: {e}'}), 502
    return _relay(r)


if __name__ == '__main__':
    url = f'http://127.0.0.1:{PORT}'
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f'Easy OKAPI admin console → {url}  (server: {SERVER_URL})')
    if not ADMIN_API_KEY:
        print('WARNING: ADMIN_API_KEY is not set — copy .env.example to .env and fill it in.')
    # 127.0.0.1 only: never expose this on the network.
    app.run(host='127.0.0.1', port=PORT, debug=False)
