import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, Response, stream_with_context, session
import jwt as pyjwt

from account import db, User
from email_service import send_verification_email, send_password_reset_email
from download_service import generate_download_token, validate_download_token, fetch_github_release

account_bp = Blueprint('account', __name__)

_APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5003')
_APP_RELEASE_TAG = os.environ.get('APP_RELEASE_TAG', 'latest')


# ── Pages ──────────────────────────────────────────────────────────────────────

@account_bp.route('/account/signup')
def signup_page():
    return render_template('signup.html')


@account_bp.route('/account/login')
def login_page():
    return render_template('login.html')


@account_bp.route('/account/forgot-password')
def forgot_password_page():
    return render_template('forgot_password.html')


@account_bp.route('/account/reset-password/<token>')
def reset_password_page(token):
    user = User.query.filter_by(reset_token=token).first()
    valid = user is not None and user.is_reset_token_valid(token)
    return render_template('reset_password.html', token=token, valid=valid)


# ── API ────────────────────────────────────────────────────────────────────────

@account_bp.route('/api/account/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    name = (data.get('name') or '').strip()
    password = data.get('password') or ''

    if not email or not name or not password:
        return jsonify({'status': 'error', 'message': 'email, name and password are required'}), 400
    if len(password) < 8:
        return jsonify({'status': 'error', 'message': 'Password must be at least 8 characters'}), 400
    if '@' not in email:
        return jsonify({'status': 'error', 'message': 'Invalid email address'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'status': 'error', 'message': 'An account with this email already exists'}), 409

    user = User(email=email, name=name)
    user.set_password(password)
    token = user.generate_verification_token()
    db.session.add(user)
    db.session.commit()

    try:
        send_verification_email(email, name, token, _APP_BASE_URL)
    except Exception as e:
        print(f'[email] Failed to send verification email to {email}: {e}')

    return jsonify({
        'status': 'success',
        'message': 'Account created. Please check your email to verify your address before downloading.'
    }), 201


@account_bp.route('/api/account/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()

    if not user:
        return render_template('verify_email.html', success=False,
                               message='Verification link is invalid or has already been used.')

    if not user.is_verification_token_valid(token):
        return render_template('verify_email.html', success=False,
                               message='Verification link has expired. Please register again or contact support.')

    user.is_verified = True
    user.verification_token = None
    user.verification_expires = None
    db.session.commit()

    return render_template('verify_email.html', success=True,
                           message='Your email has been verified. You can now log in and download Easy OKAPI.')


@account_bp.route('/api/account/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required'}), 400

    user = User.query.filter_by(email=email).first()
    # Always return success to avoid revealing whether the email exists
    if user and user.is_verified:
        token = user.generate_reset_token()
        db.session.commit()
        try:
            send_password_reset_email(email, user.name, token, _APP_BASE_URL)
        except Exception as e:
            print(f'[email] Failed to send reset email to {email}: {e}')

    return jsonify({
        'status': 'success',
        'message': 'If that email is registered, you will receive a reset link shortly.'
    })


@account_bp.route('/api/account/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('password') or ''

    if not token or not new_password:
        return jsonify({'status': 'error', 'message': 'Token and new password are required'}), 400
    if len(new_password) < 8:
        return jsonify({'status': 'error', 'message': 'Password must be at least 8 characters'}), 400

    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.is_reset_token_valid(token):
        return jsonify({'status': 'error', 'message': 'Reset link is invalid or has expired'}), 400

    user.set_password(new_password)
    user.reset_token = None
    user.reset_expires = None
    db.session.commit()

    return jsonify({'status': 'success', 'message': 'Password updated. You can now log in.'})


@account_bp.route('/api/account/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'status': 'error', 'message': 'email and password are required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'status': 'error', 'message': 'Invalid email or password'}), 401

    if not user.is_verified:
        return jsonify({
            'status': 'error',
            'message': 'Email not verified. Please check your inbox and click the verification link.'
        }), 403

    # Establish a persistent web session so the main app recognises this user
    session.permanent = True
    session['account_user_id'] = user.id
    session['account_user_name'] = user.name
    session['account_user_email'] = user.email

    # Disconnect Google Drive — session is now set so get_user_id() returns
    # the account-based key, ensuring we reset the right user's drive state.
    # We only clear the drive portion; CSV/JSON data is preserved from Firebase.
    try:
        from user_data import user_data_session
        with user_data_session() as ud:
            ud['drive'] = {
                'mode': 'guest',
                'authenticated': False,
                'folder_id': None,
                'folder_name': None,
                'credentials': None,
                'last_sync': None,
                'auto_sync_on_close': False,
                'file_mapping': {},
                'pending_oauth_state': None
            }
    except Exception as e:
        print(f'[login] Drive reset failed (non-fatal): {e}')

    download_token = generate_download_token(user.id, user.email)
    return jsonify({
        'status': 'success',
        'download_token': download_token,
        'expires_in': 1800,
        'message': 'Login successful',
        'user': {'name': user.name, 'email': user.email}
    })


@account_bp.route('/api/account/token', methods=['POST'])
def get_token():
    """Generate a fresh download token for the currently logged-in user."""
    account_id = session.get('account_user_id')
    if not account_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401

    user = User.query.get(account_id)
    if not user or not user.is_verified:
        return jsonify({'status': 'error', 'message': 'Account not found or not verified'}), 403

    download_token = generate_download_token(user.id, user.email)
    return jsonify({
        'status': 'success',
        'download_token': download_token,
        'expires_in': 1800
    })


@account_bp.route('/api/account/logout', methods=['POST'])
def logout():
    session.pop('account_user_id', None)
    session.pop('account_user_name', None)
    session.pop('account_user_email', None)
    return jsonify({'status': 'success', 'message': 'Logged out'})


@account_bp.route('/api/download')
def download():
    token = request.args.get('token') or request.headers.get('X-Download-Token')
    if not token:
        return jsonify({'status': 'error', 'message': 'Download token required'}), 401

    try:
        payload = validate_download_token(token)
    except pyjwt.ExpiredSignatureError:
        return jsonify({'status': 'error', 'message': 'Download token has expired. Please log in again.'}), 401
    except pyjwt.InvalidTokenError as e:
        return jsonify({'status': 'error', 'message': f'Invalid token: {e}'}), 401

    user = User.query.get(payload['sub'])
    if not user or not user.is_verified:
        return jsonify({'status': 'error', 'message': 'Account not found or not verified'}), 403

    version_tag = _APP_RELEASE_TAG
    try:
        upstream = fetch_github_release(version_tag)
    except Exception as e:
        print(f'[download] GitHub fetch failed: {e}')
        return jsonify({'status': 'error', 'message': 'Failed to fetch release from upstream'}), 502

    user.last_download = datetime.utcnow()
    db.session.commit()

    filename = f'easyokapi-{version_tag}.tar.gz'

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(
        stream_with_context(generate()),
        content_type='application/gzip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
