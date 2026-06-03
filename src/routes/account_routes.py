import os
import re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, Response, stream_with_context, session, redirect
import jwt as pyjwt

from account import db, User
from email_service import send_verification_email, send_password_reset_email
from download_service import (
    generate_download_token, validate_download_token,
    fetch_github_release, issue_activation_token,
    get_latest_release_tag, get_bundle_asset,
)

account_bp = Blueprint('account', __name__)

_APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5003')


def _resolved_release_tag() -> str:
    """Return the release tag to use for version checks and downloads.

    Tracks the latest published GitHub Release (no config needed). Falls back to
    'latest' so GitHub resolves to the most recent Release if the lookup fails.
    """
    return get_latest_release_tag() or 'latest'


# A semver release tag, optionally 'v'-prefixed (e.g. 'v1.1.1' or '1.1.1').
_SEMVER_TAG_RE = re.compile(r'^v?\d+\.\d+\.\d+$')


def _requested_version_tag():
    """Return a client-requested, validated release tag from ?version=, or None.

    The desktop installer pins the build it was packaged for by sending
    ?version=v1.1.1, so the server serves that exact release instead of whatever
    _resolved_release_tag() currently points at (which always tracks the latest).

    The value is interpolated into the GitHub tarball URL in fetch_github_release,
    so it MUST be validated against a strict semver allowlist — never pass an
    arbitrary client string through as a git ref. Always normalised to the
    'v'-prefixed form the git tags use. Returns None when absent or malformed so
    the caller falls back to _resolved_release_tag().
    """
    raw = (request.args.get('version') or '').strip()
    if not raw or not _SEMVER_TAG_RE.match(raw):
        return None
    return raw if raw.startswith('v') else f'v{raw}'


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
    session['last_activity'] = datetime.utcnow().isoformat()

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


@account_bp.route('/api/account/heartbeat', methods=['POST'])
def heartbeat():
    """Keep-alive ping sent by the web app while its tab is visible.

    The global idle guard (main.enforce_account_idle_timeout) refreshes
    `last_activity` for this path, so a steady heartbeat keeps the session
    alive while the user is looking at the tab. When the tab is hidden or
    closed the heartbeat stops and the session lapses after the idle timeout;
    the guard then returns 401 here (and on other /api calls) so the client
    can redirect to the login page.
    """
    if not session.get('account_user_id'):
        return jsonify({'status': 'error', 'code': 'session_expired',
                        'message': 'Not logged in'}), 401
    return jsonify({'status': 'success'})


@account_bp.route('/api/account/logout', methods=['POST'])
def logout():
    session.pop('account_user_id', None)
    session.pop('account_user_name', None)
    session.pop('account_user_email', None)
    session.pop('last_activity', None)
    return jsonify({'status': 'success', 'message': 'Logged out'})


@account_bp.route('/api/account/delete', methods=['POST'])
def delete_account():
    account_id = session.get('account_user_id')
    if not account_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401

    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''

    user = User.query.get(account_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'Account not found'}), 404
    if not user.check_password(password):
        return jsonify({'status': 'error', 'message': 'Incorrect password'}), 401

    uid = f'account_{account_id}'

    # 1. Wipe Firebase data
    try:
        from firebase_service import delete_user_data as fb_delete
        fb_delete(account_id)
    except Exception as e:
        print(f'[delete] Firebase cleanup failed (non-fatal): {e}')

    # 2. Wipe Redis / memory cache
    try:
        from user_data import purge_user_data
        purge_user_data(uid)
    except Exception as e:
        print(f'[delete] Cache purge failed (non-fatal): {e}')

    # 3. Remove from database
    db.session.delete(user)
    db.session.commit()

    # 4. Clear session
    session.clear()

    return jsonify({'status': 'success', 'message': 'Account deleted successfully'})


@account_bp.route('/api/activate', methods=['POST'])
def activate():
    """Exchange a fresh download token for a permanent activation token (AI access)."""
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'status': 'error', 'message': 'Token is required'}), 400

    try:
        payload = validate_download_token(token)
    except pyjwt.ExpiredSignatureError:
        return jsonify({'status': 'error', 'message': 'Download token has expired. Please log in again to get a new one.'}), 401
    except pyjwt.InvalidTokenError as e:
        return jsonify({'status': 'error', 'message': f'Invalid token: {e}'}), 401

    user = User.query.get(int(payload['sub']))
    if not user or not user.is_verified:
        return jsonify({'status': 'error', 'message': 'Account not found or not verified'}), 403

    activation_token = issue_activation_token(payload)
    return jsonify({'status': 'success', 'license_token': activation_token})


@account_bp.route('/api/version')
def app_version():
    """Return the current app release tag and optional release notes.

    Used by the desktop client's auto-update check (GET /update/check).
    No authentication required — version info is public.
    The version is derived from the latest successful GitHub Actions build so it
    updates automatically whenever CI publishes a new release.
    """
    tag = _resolved_release_tag()
    # Strip leading 'v' so the desktop client can do plain semver comparison
    # against state.APP_VERSION which uses the bare '1.0.X' format.
    version = tag.lstrip('v') if tag != 'latest' else tag
    return jsonify({
        'version': version,
        'release_notes': os.environ.get('APP_RELEASE_NOTES', ''),
    })


@account_bp.route('/api/download')
def download():
    # Accept token from query param, X-Download-Token header, or Authorization: Bearer header.
    # The desktop auto-updater sends its permanent activation token as Authorization: Bearer.
    # validate_download_token() accepts activation tokens too (same purpose claim, no exp).
    auth_header = request.headers.get('Authorization', '')
    bearer = auth_header[7:] if auth_header.startswith('Bearer ') else None
    token = request.args.get('token') or request.headers.get('X-Download-Token') or bearer
    if not token:
        return jsonify({'status': 'error', 'message': 'Download token required'}), 401

    try:
        payload = validate_download_token(token)
    except pyjwt.ExpiredSignatureError:
        return jsonify({'status': 'error', 'message': 'Download token has expired. Please log in again.'}), 401
    except pyjwt.InvalidTokenError as e:
        return jsonify({'status': 'error', 'message': f'Invalid token: {e}'}), 401

    user = User.query.get(int(payload['sub']))
    if not user or not user.is_verified:
        return jsonify({'status': 'error', 'message': 'Account not found or not verified'}), 403

    # Honour an explicit, validated ?version= (the installer pins its own build);
    # fall back to the server's resolved tag (used by the in-app auto-updater,
    # which intentionally always pulls the latest).
    version_tag = _requested_version_tag() or _resolved_release_tag()

    # No-source binary-swap updater: serve the per-platform onedir *bundle* asset
    # (EasyOKAPI-bundle-{mac,linux}.tar.gz / -win.zip) instead of the source
    # tarball. The desktop client sends ?kind=bundle&platform=mac|win|linux and
    # follows the redirect to the release asset's public download URL. (Frozen
    # builds have no .py on disk, so they swap the whole onedir — see the desktop
    # repo's update_service._download_and_stage_bundle.)
    if request.args.get('kind') == 'bundle':
        platform = (request.args.get('platform') or '').strip().lower()
        if platform not in ('mac', 'win', 'linux'):
            return jsonify({'status': 'error', 'message': 'Invalid or missing platform'}), 400
        asset = get_bundle_asset(platform, version_tag)
        if not asset or not asset.get('browser_download_url'):
            return jsonify({'status': 'error',
                            'message': f'No {platform} bundle published for release {version_tag}'}), 404
        user.last_download = datetime.utcnow()
        db.session.commit()
        return redirect(asset['browser_download_url'], code=302)

    try:
        upstream = fetch_github_release(version_tag)
    except Exception as e:
        print(f'[download] GitHub fetch failed for tag={version_tag!r}: {e}')
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
