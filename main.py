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
from download_service import get_cached_artifacts, _ARTIFACT_PREFIX
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
# GitHub Artifact Downloads
# (artifact cache + _ARTIFACT_PREFIX live in download_service.py)
# ------------------------------------------------------------------

@app.route('/api/release-info')
def api_release_info():
    try:
        artifacts = get_cached_artifacts()
        version, available = None, {p: False for p in _ARTIFACT_PREFIX}
        for art in artifacts:
            if art.get('expired'):
                continue
            for platform, prefix in _ARTIFACT_PREFIX.items():
                if art['name'].startswith(prefix):
                    available[platform] = True
                    if version is None:
                        version = art['name'][len(prefix):]  # e.g. "v1.0.4"
        return jsonify({'version': version or 'unknown', 'available': available})
    except Exception as e:
        return jsonify({'error': str(e), 'version': None, 'available': {}}), 502

@app.route('/download/<platform>')
def download_offline(platform):
    if platform not in _ARTIFACT_PREFIX:
        return jsonify({'status': 'error', 'message': 'Unknown platform'}), 404
    if not os.environ.get('GITHUB_TOKEN'):
        return jsonify({'status': 'error', 'message': 'GITHUB_TOKEN not configured on server'}), 503
    try:
        artifacts = get_cached_artifacts()
        prefix = _ARTIFACT_PREFIX[platform]
        artifact = next(
            (a for a in artifacts if a['name'].startswith(prefix) and not a.get('expired')),
            None
        )
        if not artifact:
            return jsonify({'status': 'error', 'message': f'No {platform} build available yet'}), 404
        # Ask GitHub for the presigned S3 URL (returns 302)
        dl = http_requests.get(
            f'https://api.github.com/repos/{_GITHUB_REPO}/actions/artifacts/{artifact["id"]}/zip',
            headers=_gh_headers(), allow_redirects=False, timeout=10
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