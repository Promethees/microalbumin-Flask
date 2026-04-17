from flask import Flask, render_template, request, jsonify, make_response
import os
import sys
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

# Initialize SocketIO with app
socketio.init_app(app)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(file_bp)
app.register_blueprint(data_bp)
app.register_blueprint(math_bp)

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
                         production_mode= app.config['PRODUCTION_MODE']))
    return response

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