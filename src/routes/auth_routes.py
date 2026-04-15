from flask import Blueprint, request, jsonify, render_template, session
from user_data import (
    get_user_data, get_user_id, set_pending_oauth_state, get_pending_oauth_state,
    set_drive_credentials, set_drive_folder, disconnect_drive, set_drive_preference
)
from google_drive_service import (
    get_drive_service, get_authorization_url, exchange_code_for_credentials,
    list_folders, create_folder, sync_session_to_drive, load_drive_to_session
)
import secrets

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/auth/google', methods=['GET'])
def auth_google():
    """Initiate OAuth 2.0 flow for Google Drive."""
    try:
        token = secrets.token_urlsafe(32)
        uid = get_user_id()
        state_payload = f"{uid}|{token}"
        authorization_url, _ = get_authorization_url(state=state_payload)
        set_pending_oauth_state(state_payload)
        return jsonify({'status': 'success', 'authorization_url': authorization_url})
    except FileNotFoundError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to initiate OAuth: {str(e)}'}), 500

@auth_bp.route('/auth/google/callback', methods=['GET'])
def auth_google_callback():
    """Handle OAuth 2.0 callback from Google."""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        
        if state and '|' in state:
            parts = state.split('|')
            if len(parts) >= 2:
                recovered_uid = parts[0]
                current_uid = session.get('user_id')
                if not current_uid or current_uid != recovered_uid:
                    print(f"[INFO] Recovering session for user: {recovered_uid}")
                    session['user_id'] = recovered_uid
        
        pending_state = get_pending_oauth_state()
        if state != pending_state:
            debug_info = {
                'url_state': state,
                'pending_server_state': pending_state, 
                'session_content': {k: v for k, v in session.items() if k != '_id'}
            }
            return render_template('callback.html', 
                                status='error', 
                                message='Invalid state parameter', 
                                debug=debug_info), 400
        
        credentials = exchange_code_for_credentials(code, state)
        set_drive_credentials(credentials.to_json())
        return render_template('callback.html', status='success')
    except Exception as e:
        return render_template('callback.html', status='error', message=f'Authentication failed: {str(e)}'), 500

@auth_bp.route('/auth/google/status', methods=['GET'])
def auth_google_status():
    """Check Google Drive authentication status."""
    try:
        user_data = get_user_data()
        drive_data = user_data.get('drive', {})
        return jsonify({
            'status': 'success',
            'authenticated': drive_data.get('authenticated', False),
            'mode': drive_data.get('mode', 'guest'),
            'folder_id': drive_data.get('folder_id'),
            'folder_name': drive_data.get('folder_name'),
            'last_sync': drive_data.get('last_sync'),
            'auto_sync_on_close': drive_data.get('auto_sync_on_close', False)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/auth/google/logout', methods=['POST'])
def auth_google_logout():
    """Disconnect Google Drive and return to guest mode."""
    from extensions import socketio
    try:
        disconnect_drive()
        socketio.emit('update_csv')
        socketio.emit('update_json', {'mode': 'kinetics'})
        socketio.emit('update_json', {'mode': 'point'})
        return jsonify({'status': 'success', 'message': 'Disconnected from Google Drive'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/folder/list', methods=['GET'])
def drive_folder_list():
    """List Google Drive folders, optionally under a specific parent."""
    try:
        service = get_drive_service()
        if not service:
            return jsonify({'status': 'error', 'message': 'Not authenticated'}), 401
        parent_id = request.args.get('parent_id', 'root')
        folders = list_folders(service, parent_id=parent_id)
        return jsonify({'status': 'success', 'folders': folders})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/folder/create', methods=['POST'])
def drive_folder_create():
    """Create a new folder in Google Drive."""
    try:
        service = get_drive_service()
        if not service:
            return jsonify({'status': 'error', 'message': 'Not authenticated'}), 401
        folder_name = request.json.get('folder_name', 'Easy OKAPI Data')
        parent_id = request.json.get('parent_id', 'root')
        folder = create_folder(service, folder_name, parent_id)
        if folder:
            return jsonify({'status': 'success', 'folder': folder})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to create folder'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/folder/select', methods=['POST'])
def drive_folder_select():
    """Set selected folder as storage location."""
    try:
        folder_id = request.json.get('folder_id')
        folder_name = request.json.get('folder_name')
        if not folder_id or not folder_name:
            return jsonify({'status': 'error', 'message': 'folder_id and folder_name required'}), 400
        set_drive_folder(folder_id, folder_name)
        return jsonify({'status': 'success', 'message': f'Selected folder: {folder_name}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/sync', methods=['POST'])
def drive_sync():
    """Sync session data to Google Drive."""
    try:
        result = sync_session_to_drive()
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/load', methods=['POST'])
def drive_load():
    """Load data from Google Drive to session."""
    from main import socketio
    try:
        result = load_drive_to_session()
        socketio.emit('update_csv')
        socketio.emit('update_json', {'mode': 'kinetics'})
        socketio.emit('update_json', {'mode': 'point'})
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/preferences/set', methods=['POST'])
def drive_preferences_set():
    """Update user Drive preferences."""
    try:
        key = request.json.get('key')
        value = request.json.get('value')
        if not key:
            return jsonify({'status': 'error', 'message': 'key required'}), 400
        set_drive_preference(key, value)
        return jsonify({'status': 'success', 'message': f'Updated {key}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@auth_bp.route('/drive/preferences/get', methods=['GET'])
def drive_preferences_get():
    """Get current user Drive preferences."""
    try:
        user_data = get_user_data()
        drive_data = user_data.get('drive', {})
        return jsonify({
            'status': 'success',
            'preferences': {
                'auto_sync_on_close': drive_data.get('auto_sync_on_close', False),
                'last_sync': drive_data.get('last_sync')
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
