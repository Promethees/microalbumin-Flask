from flask import Flask, render_template, request, jsonify, make_response, send_from_directory, redirect, session
import os
import sys
import requests as http_requests
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

# Add src to path
sys.path.append('src')
from user_data import init_user_data
from range import get_range_input
from mode import get_mode_input
from quantity import get_quantity_input
from config import Config
from extensions import socketio

# Import Blueprints
from routes.auth_routes import auth_bp
from routes.file_routes import file_bp
from routes.data_routes import data_bp
from routes.math_routes import math_bp
from routes.ai_routes import ai_bp
from routes.account_routes import account_bp
from download_service import get_release, get_release_asset, _RELEASE_ASSET_SUFFIX, _gh_headers
from routes.oauth_routes import oauth_bp
from account import db, run_migrations

app = Flask(__name__, static_folder='static')
app.config.from_object(Config)

# Production Security & Session handling
if not app.debug:
    # Use ProxyFix to handle HTTPS behind Heroku's proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    # Ensure cookies are sent over HTTPS and during OAuth redirects
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_HTTPONLY'] = True

# Initialize SocketIO and SQLAlchemy with app
socketio.init_app(app)
db.init_app(app)

# Create account tables on first run, then apply any schema migrations
with app.app_context():
    db.create_all()
    run_migrations(db.engine)

import firebase_service as _fb
_fb.prewarm()  # builds credentials object only; no network call at startup

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(file_bp)
app.register_blueprint(data_bp)
app.register_blueprint(math_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(account_bp)
app.register_blueprint(oauth_bp)

delimiter = "/"

# Region 1: Base Routes
@app.route('/ping')
def ping():
    return jsonify({'status': 'success'})

@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    try:
        response = make_response(jsonify({
            'status': 'success',
            'message': 'Clearing client-side cache',
            'action': 'clear_storage'
        }))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@app.route('/')
def index():
    # Initialize user data storage
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    user_data = init_user_data()
    file_list = list(user_data['csv'].keys())
    cal_json_list = list(user_data['json'].get('kinetics', {}).keys())
    
    account_user = None
    if session.get('account_user_id'):
        account_user = {
            'id': session['account_user_id'],
            'name': session.get('account_user_name', ''),
            'email': session.get('account_user_email', '')
        }

    response = make_response(render_template('index.html',
                         title="Easy OKAPI",
                         directory= '/',
                         csv_path = '/csv',
                         range_input=range_input,
                         mode_input=mode_input,
                         quantity_input=quantity_input,
                         file_list=file_list,
                         cal_json_list=cal_json_list,
                         delimiter=delimiter,
                         production_mode= app.config['PRODUCTION_MODE'],
                         account_user=account_user))
    return response

# ------------------------------------------------------------------
# GitHub Release Downloads
# Installers are served from the GitHub Release pinned by APP_RELEASE_TAG
# (release cache + _RELEASE_ASSET_SUFFIX live in download_service.py).
# ------------------------------------------------------------------

@app.route('/api/release-info')
def api_release_info():
    try:
        release = get_release()
        version = (release.get('tag_name') if release else None) or 'unknown'  # e.g. "v1.1.4"
        available = {p: get_release_asset(p) is not None for p in _RELEASE_ASSET_SUFFIX}
        return jsonify({'version': version, 'available': available})
    except Exception as e:
        return jsonify({'error': str(e), 'version': None, 'available': {}}), 502

@app.route('/download/<platform>')
def download_offline(platform):
    if platform not in _RELEASE_ASSET_SUFFIX:
        return jsonify({'status': 'error', 'message': 'Unknown platform'}), 404
    try:
        asset = get_release_asset(platform)
        if not asset:
            return jsonify({'status': 'error', 'message': f'No {platform} build available yet'}), 404
        # Ask GitHub for the presigned S3 URL (the asset API 302-redirects to it).
        dl = http_requests.get(
            asset['url'],
            headers={**_gh_headers(), 'Accept': 'application/octet-stream'},
            allow_redirects=False, timeout=10
        )
        location = dl.headers.get('Location')
        if not location:
            return jsonify({'status': 'error', 'message': 'Could not resolve download URL'}), 502
        return redirect(location)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 502

@app.route("/api/current_output", methods=["GET"])
def api_current_output():
    return jsonify({"exists": False, "message": "Not supported in multiuser mode"}), 404

if __name__ == '__main__':
    import eventlet
    port = int(os.environ.get('PORT', 5003))
    host = '0.0.0.0'
    try:
        socketio.run(app, debug=False, host=host, port=port)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)