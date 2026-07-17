import os
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, Response, stream_with_context, session, redirect
import jwt as pyjwt

from account import db, User, LicenseMachine
from email_service import (
    send_verification_email, send_password_reset_email, send_license_revoked_email,
    send_account_banned_email,
)
from download_service import (
    generate_download_token, validate_download_token,
    fetch_github_release, issue_activation_token, validate_activation_token,
    get_latest_release_tag, get_bundle_asset, resolve_asset_location,
    _activation_public_key,
)
from rate_limit import limiter, ACTIVATE_LIMIT, LICENSE_CHECK_LIMIT, REGISTER_LIMIT

account_bp = Blueprint('account', __name__)

_APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5003')

# Shown to a banned account on every blocked surface (login, token, activate,
# download). A ban is account-wide; contact support to appeal.
_BAN_MESSAGE = ('This account has been suspended. Please contact support if you '
                'believe this is a mistake.')

# How many distinct machines one license may be activated on at once. Default 1
# (a license is locked to a single machine); raise via env for multi-seat plans.
# Guard the parse so a malformed env var can never crash the app at import time.
try:
    _MAX_MACHINES = max(1, int(os.environ.get('MAX_MACHINES_PER_LICENSE', '1')))
except (TypeError, ValueError):
    _MAX_MACHINES = 1


def _normalise_hwid(value):
    """A machine fingerprint is a 64-char lowercase hex SHA-256 (see client hwid.py).

    Returns the cleaned value, or '' if it is missing/malformed (treated as "no
    fingerprint supplied" → no hardware lock applied for that request).
    """
    h = (value or '').strip().lower()
    if len(h) == 64 and all(c in '0123456789abcdef' for c in h):
        return h
    return ''


def _bind_machine(user, hwid):
    """Record `hwid` as one of the user's licensed machines, enforcing the seat cap.

    Returns (ok: bool, message: str). Re-activating an already-bound machine always
    succeeds (and refreshes last_seen). A new machine is bound only while the user
    is under _MAX_MACHINES; otherwise it is refused so the license cannot silently
    spread to extra machines.
    """
    machines = LicenseMachine.query.filter_by(user_id=user.id).all()
    for m in machines:
        if m.hwid == hwid:
            m.last_seen = datetime.utcnow()
            db.session.commit()
            return True, 'already bound'
    if len(machines) >= _MAX_MACHINES:
        return False, (
            f'This license is already activated on {_MAX_MACHINES} machine(s). '
            'Deactivate one from your account before activating a new machine.'
        )
    db.session.add(LicenseMachine(user_id=user.id, hwid=hwid, last_seen=datetime.utcnow()))
    db.session.commit()
    return True, 'bound'


def _machine_is_licensed(user, payload, presented_hwid):
    """Confirm a permanent token is being used from the machine it is bound to.

    Legacy tokens (no 'hwid' claim) are grandfathered → always allowed. For a
    hardware-locked token, the caller must present (X-Machine-Id / body hwid) the
    same fingerprint the token carries, and that machine must still be a bound seat
    for this user. Refreshes last_seen on success.

    A whole-account ban (User.banned) overrides everything below: no machine is
    licensed, so the AI proxy, in-app auto-update, and /api/license/check (→
    'revoked') all stop immediately for every machine — even a legacy unbound
    token. This is the single choke point that makes a ban a superset of a
    per-seat revocation.
    """
    if getattr(user, 'banned', False):
        return False
    token_hwid = payload.get('hwid')
    if not token_hwid:
        return True  # legacy, unbound token
    if _normalise_hwid(presented_hwid) != token_hwid:
        return False
    m = LicenseMachine.query.filter_by(user_id=user.id, hwid=token_hwid).first()
    if not m or m.revoked:
        return False  # no seat, or the admin has revoked this license
    m.last_seen = datetime.utcnow()
    db.session.commit()
    return True


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
@limiter.limit(REGISTER_LIMIT)
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

    # Reply identically whether or not the email is already registered, so this
    # endpoint cannot be used to enumerate which addresses have accounts. The
    # neutral message below is returned in every non-validation case.
    _NEUTRAL_MSG = 'Account created. Please check your email to verify your address before downloading.'

    existing = User.query.filter_by(email=email).first()
    if existing:
        # Never confirm the account exists. For an unverified account, silently
        # re-send the verification link so a legitimate re-signup still works;
        # for a verified account, do nothing. Either way the response is the same.
        if not existing.is_verified:
            try:
                token = existing.generate_verification_token()
                db.session.commit()
                send_verification_email(email, existing.name, token, _APP_BASE_URL)
            except Exception as e:
                print(f'[email] Verification resend on duplicate signup failed for {email}: {e}')
        return jsonify({'status': 'success', 'message': _NEUTRAL_MSG}), 201

    user = User(email=email, name=name)
    user.set_password(password)
    token = user.generate_verification_token()
    db.session.add(user)
    db.session.commit()

    try:
        send_verification_email(email, name, token, _APP_BASE_URL)
    except Exception as e:
        print(f'[email] Failed to send verification email to {email}: {e}')

    return jsonify({'status': 'success', 'message': _NEUTRAL_MSG}), 201


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

    if user.banned:
        return jsonify({'status': 'error', 'code': 'account_banned',
                        'message': _BAN_MESSAGE}), 403

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
    if user.banned:
        return jsonify({'status': 'error', 'code': 'account_banned',
                        'message': _BAN_MESSAGE}), 403

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
    # Drop the pre-login guest workspace too. Otherwise a guest who connected
    # Google Drive (loaded files + stored OAuth credentials) before signing in
    # would see that stale workspace — and an active Drive connection — resurface
    # after logout. Purging the blob clears the credentials; popping 'user_id'
    # forces a fresh guest UUID on the next request.
    guest_uid = session.get('user_id')
    if guest_uid:
        try:
            from user_data import purge_user_data
            purge_user_data(guest_uid)
        except Exception as e:
            print(f'[logout] Guest data purge failed (non-fatal): {e}')
    for key in ('account_user_id', 'account_user_name', 'account_user_email',
                'last_activity', 'user_id'):
        session.pop(key, None)
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
@limiter.limit(ACTIVATE_LIMIT)
def activate():
    """Exchange a fresh download token for a permanent, hardware-locked activation token.

    The client sends its machine fingerprint (`hwid`); we bind it to the user's
    license (subject to the seat cap) and embed it in the issued token so the token
    only works on that machine. Omitting `hwid` yields an unbound token (legacy
    clients / degraded hosts), preserving backward compatibility.
    """
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    hwid = _normalise_hwid(data.get('hwid'))
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
    if user.banned:
        return jsonify({'status': 'error', 'code': 'account_banned',
                        'message': _BAN_MESSAGE}), 403

    if hwid:
        ok, message = _bind_machine(user, hwid)
        if not ok:
            return jsonify({'status': 'error', 'code': 'machine_limit', 'message': message}), 409

    activation_token = issue_activation_token(payload, hwid or None)
    return jsonify({'status': 'success', 'license_token': activation_token})


@account_bp.route('/api/license/check', methods=['POST'])
@limiter.limit(LICENSE_CHECK_LIMIT)
def license_check():
    """Lightweight 'is this license still good for this machine?' poll.

    The desktop client posts its stored permanent activation token + machine
    fingerprint; we answer 'active' or 'revoked' so the client can enforce admin
    revocation locally (the token itself is permanent and verifies offline, so the
    client cannot tell on its own that the admin has revoked it).

    Always replies HTTP 200 with a `status` of 'active' or 'revoked' for the normal
    cases, so the client has a single field to key off. A revoked verdict means:
    account gone/unverified, the seat was deactivated/transferred, or the admin
    revoked it. A malformed/missing token is a 400 (client bug, not a verdict) —
    the client treats anything that is not an explicit 'revoked' as "no change", so
    a server hiccup never wrongly blocks a paying user.
    """
    data = request.get_json(silent=True) or {}
    token = (data.get('license_token') or '').strip()
    hwid = data.get('hwid')
    if not token:
        return jsonify({'status': 'error', 'message': 'license_token is required'}), 400
    try:
        payload = validate_activation_token(token)
    except pyjwt.InvalidTokenError:
        # Signature/format we cannot trust. Not a revocation verdict — let the
        # client keep its current state rather than block on a server-key mismatch.
        return jsonify({'status': 'error', 'code': 'invalid_token',
                        'message': 'Token could not be validated'}), 401

    user = User.query.get(int(payload['sub']))
    if not user or not user.is_verified:
        return jsonify({'status': 'revoked', 'code': 'account_invalid'}), 200
    if user.banned:
        # Account-wide ban. Report 'revoked' (a distinct code for diagnostics) so
        # the desktop client's existing revocation gate blocks the app — no client
        # change is needed to enforce a ban.
        return jsonify({'status': 'revoked', 'code': 'account_banned'}), 200
    if _machine_is_licensed(user, payload, hwid):
        return jsonify({'status': 'active'}), 200
    return jsonify({'status': 'revoked', 'code': 'machine_mismatch'}), 200


@account_bp.route('/api/license/release', methods=['POST'])
@limiter.limit(LICENSE_CHECK_LIMIT)
def license_release():
    """Free the seat of the machine making the call, so uninstalling frees a seat.

    The web-session route (/api/account/machines/deactivate) can only be driven by
    a user who signs in and clicks; nothing frees the seat when the software is
    simply uninstalled, so a user who reinstalls on a new machine hits the seat cap
    with a stale seat held by a machine that no longer exists. The uninstallers
    call this before deleting anything.

    Auth is the machine's own permanent token — there is no session at uninstall
    time. The token is RS256-signed and carries the 'hwid' claim of the machine it
    is bound to, so possessing it proves the caller is that machine, and it can
    only ever release ITS OWN seat (the claim names the seat; a body `hwid`, if
    sent, must agree with it). That is strictly weaker than what the token already
    grants, so this adds no new authority.

    Refuses to free a revoked seat or a banned account's seat: deleting the row
    would let the user re-activate the same machine into a fresh, unrevoked seat
    and walk out of the admin kill-switch.

    Idempotent — an already-freed seat, an unbound legacy token, or a deleted
    account all report success, so an uninstaller never has to retry or block.
    """
    data = request.get_json(silent=True) or {}
    token = (data.get('license_token') or '').strip()
    if not token:
        return jsonify({'status': 'error', 'message': 'license_token is required'}), 400
    try:
        payload = validate_activation_token(token)
    except pyjwt.InvalidTokenError:
        return jsonify({'status': 'error', 'code': 'invalid_token',
                        'message': 'Token could not be validated'}), 401

    token_hwid = payload.get('hwid')
    if not token_hwid:
        # Legacy, unbound token: it never consumed a seat, so there is nothing to
        # free. Success — and note it cannot name a seat, which is exactly why we
        # never fall back to a body-supplied hwid here (that would let any legacy
        # token free any machine's seat).
        return jsonify({'status': 'success', 'code': 'not_bound',
                        'message': 'Token is not bound to a machine'}), 200
    presented = _normalise_hwid(data.get('hwid'))
    if presented and presented != token_hwid:
        return jsonify({'status': 'error', 'code': 'machine_mismatch',
                        'message': 'Token is not bound to this machine'}), 403

    user = User.query.get(int(payload['sub']))
    if not user:
        return jsonify({'status': 'success', 'code': 'account_invalid',
                        'message': 'No account to release from'}), 200
    if user.banned:
        return jsonify({'status': 'error', 'code': 'account_banned',
                        'message': _BAN_MESSAGE}), 403

    m = LicenseMachine.query.filter_by(user_id=user.id, hwid=token_hwid).first()
    if not m:
        return jsonify({'status': 'success', 'code': 'not_bound',
                        'message': 'Machine is not activated'}), 200
    if m.revoked:
        return jsonify({'status': 'error', 'code': 'seat_revoked',
                        'message': 'This license has been deactivated by support'}), 403
    db.session.delete(m)
    db.session.commit()
    return jsonify({'status': 'success', 'code': 'released',
                    'message': 'Machine deactivated'}), 200


@account_bp.route('/api/activation-pubkey')
def activation_pubkey():
    """Public key used to verify permanent activation tokens (RS256).

    Public by design — it can only verify tokens, never mint them. The desktop
    client embeds its own copy; this endpoint exists for diagnostics and so an
    installer could fetch the current key if needed.
    """
    pem = _activation_public_key()
    if not pem:
        return jsonify({'status': 'error', 'message': 'Activation signing key not configured'}), 503
    return jsonify({'status': 'success', 'public_key': pem})


@account_bp.route('/api/account/machines', methods=['GET'])
def list_machines():
    """List the machines the logged-in user's license is activated on."""
    account_id = session.get('account_user_id')
    if not account_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    machines = LicenseMachine.query.filter_by(user_id=account_id).order_by(LicenseMachine.activated_at).all()
    return jsonify({
        'status': 'success',
        'max_machines': _MAX_MACHINES,
        'machines': [{
            'id': m.id,
            'hwid': m.hwid,
            'label': m.label,
            'activated_at': m.activated_at.isoformat() if m.activated_at else None,
            'last_seen': m.last_seen.isoformat() if m.last_seen else None,
        } for m in machines],
    })


@account_bp.route('/api/account/machines/deactivate', methods=['POST'])
def deactivate_machine():
    """Free a machine seat so the license can be moved (license transfer).

    Accepts {hwid} or {id}. After deactivation the token on that machine stops
    passing the server-side machine check; the user can activate a new machine.

    A revoked seat or a banned account cannot be freed here: deleting the row and
    re-activating would mint a fresh, unrevoked seat for the same machine and
    escape the admin kill-switch. Mirrors /api/license/release.
    """
    account_id = session.get('account_user_id')
    if not account_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    user = User.query.get(account_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    if user.banned:
        return jsonify({'status': 'error', 'message': _BAN_MESSAGE}), 403
    data = request.get_json(silent=True) or {}
    q = LicenseMachine.query.filter_by(user_id=account_id)
    if data.get('id') is not None:
        m = q.filter_by(id=data.get('id')).first()
    else:
        m = q.filter_by(hwid=_normalise_hwid(data.get('hwid'))).first()
    if not m:
        return jsonify({'status': 'error', 'message': 'Machine not found'}), 404
    if m.revoked:
        return jsonify({'status': 'error',
                        'message': 'This license has been deactivated by support'}), 403
    db.session.delete(m)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Machine deactivated'})


# ── Admin license control (shared-secret) ────────────────────────────────────
# A tiny machine-to-machine surface for the local admin tool (the `offline`
# branch). Guarded by ADMIN_API_KEY rather than a user session — there is no admin
# UI on the server. With no key configured the endpoints refuse all callers (503),
# so an unconfigured deployment can never be revoke-controlled by accident.

def _require_admin():
    """Return None when the request carries the right admin key, else an error tuple.

    Constant-time compare so the key can't be guessed by timing. The key lives only
    in the server's ADMIN_API_KEY env var and the admin's local tool — never in any
    client build."""
    import hmac
    configured = os.environ.get('ADMIN_API_KEY', '')
    if not configured:
        return jsonify({'status': 'error', 'message': 'Admin control is not configured'}), 503
    presented = request.headers.get('X-Admin-Key', '')
    if not hmac.compare_digest(presented, configured):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    return None


def _machine_view(m):
    return {
        'id': m.id,
        'hwid': m.hwid,
        'label': m.label,
        'revoked': bool(m.revoked),
        'activated_at': m.activated_at.isoformat() if m.activated_at else None,
        'last_seen': m.last_seen.isoformat() if m.last_seen else None,
        'revoked_at': m.revoked_at.isoformat() if m.revoked_at else None,
    }


@account_bp.route('/api/admin/lookup')
def admin_lookup():
    """Look up an account and its machine seats by email (admin tool, read-only)."""
    err = _require_admin()
    if err:
        return err
    email = (request.args.get('email') or '').strip().lower()
    if not email:
        return jsonify({'status': 'error', 'message': 'email is required'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'status': 'error', 'message': 'Account not found'}), 404
    machines = LicenseMachine.query.filter_by(user_id=user.id).order_by(LicenseMachine.activated_at).all()
    return jsonify({
        'status': 'success',
        'user': {'id': user.id, 'email': user.email, 'name': user.name,
                 'is_verified': bool(user.is_verified),
                 'banned': bool(user.banned),
                 'banned_at': user.banned_at.isoformat() if user.banned_at else None},
        'machines': [_machine_view(m) for m in machines],
    })


@account_bp.route('/api/admin/users')
def admin_users():
    """List registered accounts for the admin console, newest first (read-only).

    Optional `q` filters by case-insensitive substring of email OR name. `limit`
    caps the result (default 200, hard max 500) so a huge user base can't return an
    unbounded payload. Each row carries a machine count and whether any seat is
    revoked, so the console can show license status at a glance.
    """
    err = _require_admin()
    if err:
        return err
    q = (request.args.get('q') or '').strip().lower()
    try:
        limit = min(500, max(1, int(request.args.get('limit', 200))))
    except (TypeError, ValueError):
        limit = 200
    query = User.query
    if q:
        like = '%' + q + '%'
        query = query.filter(db.or_(db.func.lower(User.email).like(like),
                                    db.func.lower(User.name).like(like)))
    total = query.count()
    users = query.order_by(User.created_at.desc()).limit(limit).all()
    rows = []
    for u in users:
        machines = u.machines  # backref; admin-scale N+1 is fine
        rows.append({
            'id': u.id,
            'email': u.email,
            'name': u.name,
            'is_verified': bool(u.is_verified),
            'banned': bool(u.banned),
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'machine_count': len(machines),
            'revoked': any(m.revoked for m in machines),
        })
    return jsonify({
        'status': 'success',
        'count': len(rows),
        'total': total,           # total matching before the limit
        'limit': limit,
        'users': rows,
    })


@account_bp.route('/api/admin/revoke', methods=['POST'])
def admin_revoke():
    """Revoke (or reinstate) a user's license across all their machines, by email.

    Body: {"email": "...", "revoked": true|false}. On revoke=true every seat is
    marked revoked (the server-side kill-switch) and a notification email is sent
    once to the user; revoked=false reinstates every seat (no email). Idempotent.
    """
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    revoke = bool(data.get('revoked', True))
    if not email:
        return jsonify({'status': 'error', 'message': 'email is required'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'status': 'error', 'message': 'Account not found'}), 404

    machines = LicenseMachine.query.filter_by(user_id=user.id).all()
    affected = 0
    now = datetime.utcnow()
    for m in machines:
        if bool(m.revoked) != revoke:
            m.revoked = revoke
            m.revoked_at = now if revoke else None
            affected += 1
    db.session.commit()

    email_sent = False
    if revoke and affected:
        try:
            send_license_revoked_email(user.email, user.name, _APP_BASE_URL)
            email_sent = True
        except Exception:
            email_sent = False  # best-effort: revocation still stands

    return jsonify({
        'status': 'success',
        'revoked': revoke,
        'affected': affected,
        'machine_count': len(machines),
        'email_sent': email_sent,
        'machines': [_machine_view(m) for m in machines],
    })


@account_bp.route('/api/admin/ban', methods=['POST'])
def admin_ban():
    """Ban (or unban) a whole account by email — the admin kill-switch's big hammer.

    Body: {"email": "...", "banned": true|false}. A ban is broader than a license
    revocation: it sets User.banned, which blocks web sign-in, download, activation
    AND software usage on every machine (the desktop client's license check then
    reports 'revoked', so its existing gate locks the app). On ban=true a seat is
    NOT required — even an account with zero machines is fully blocked — and every
    seat is also marked revoked so the AI proxy / auto-update stop immediately; a
    notification email is sent once. banned=false lifts the ban and reinstates
    every seat (no email). Idempotent.
    """
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    ban = bool(data.get('banned', True))
    if not email:
        return jsonify({'status': 'error', 'message': 'email is required'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'status': 'error', 'message': 'Account not found'}), 404

    now = datetime.utcnow()
    changed = bool(user.banned) != ban
    user.banned = ban
    user.banned_at = now if ban else None

    # Keep the per-seat revoked flag in lockstep so the seat-level surfaces
    # (AI proxy, auto-update) reflect the ban without depending on User.banned.
    machines = LicenseMachine.query.filter_by(user_id=user.id).all()
    for m in machines:
        if bool(m.revoked) != ban:
            m.revoked = ban
            m.revoked_at = now if ban else None
    db.session.commit()

    email_sent = False
    if ban and changed:
        try:
            send_account_banned_email(user.email, user.name, _APP_BASE_URL)
            email_sent = True
        except Exception:
            email_sent = False  # best-effort: the ban still stands

    return jsonify({
        'status': 'success',
        'banned': ban,
        'changed': changed,
        'machine_count': len(machines),
        'email_sent': email_sent,
        'user': {'id': user.id, 'email': user.email, 'name': user.name,
                 'is_verified': bool(user.is_verified), 'banned': bool(user.banned),
                 'banned_at': user.banned_at.isoformat() if user.banned_at else None},
        'machines': [_machine_view(m) for m in machines],
    })


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
    # Two credential paths:
    #   * Authorization: Bearer <permanent activation token>  — the desktop
    #     auto-updater. Validated as an activation token (RS256/legacy HS256) and
    #     hardware-checked against X-Machine-Id.
    #   * ?token= / X-Download-Token <short-lived download token> — the installer
    #     fetching the source tarball. Validated as a download token (exp enforced).
    auth_header = request.headers.get('Authorization', '')
    bearer = auth_header[7:] if auth_header.startswith('Bearer ') else None
    short_token = request.args.get('token') or request.headers.get('X-Download-Token')
    # The permanent activation (Bearer) credential belongs to a frozen desktop
    # build, which auto-updates by swapping the compiled onedir *bundle* and has
    # no .py on disk. It must therefore NEVER be able to pull the raw Python
    # source tarball — only the installer's short-lived download token may.
    via_activation = bool(bearer)

    if bearer:
        try:
            payload = validate_activation_token(bearer)
        except pyjwt.InvalidTokenError as e:
            return jsonify({'status': 'error', 'message': f'Invalid token: {e}'}), 401
        user = User.query.get(int(payload['sub']))
        if not user or not user.is_verified:
            return jsonify({'status': 'error', 'message': 'Account not found or not verified'}), 403
        if user.banned:
            return jsonify({'status': 'error', 'code': 'account_banned',
                            'message': _BAN_MESSAGE}), 403
        if not _machine_is_licensed(user, payload, request.headers.get('X-Machine-Id')):
            return jsonify({'status': 'error', 'code': 'machine_mismatch',
                            'message': 'This license is not activated on this machine.'}), 403
    elif short_token:
        try:
            payload = validate_download_token(short_token)
        except pyjwt.ExpiredSignatureError:
            return jsonify({'status': 'error', 'message': 'Download token has expired. Please log in again.'}), 401
        except pyjwt.InvalidTokenError as e:
            return jsonify({'status': 'error', 'message': f'Invalid token: {e}'}), 401
        user = User.query.get(int(payload['sub']))
        if not user or not user.is_verified:
            return jsonify({'status': 'error', 'message': 'Account not found or not verified'}), 403
        if user.banned:
            return jsonify({'status': 'error', 'code': 'account_banned',
                            'message': _BAN_MESSAGE}), 403
    else:
        return jsonify({'status': 'error', 'message': 'Download token required'}), 401

    # Honour an explicit, validated ?version= (the installer pins its own build);
    # fall back to the server's resolved tag (used by the in-app auto-updater,
    # which intentionally always pulls the latest).
    version_tag = _requested_version_tag() or _resolved_release_tag()

    # No-source binary-swap updater: serve the per-platform onedir *bundle* asset
    # (EasyOKAPI-bundle-{mac,linux}.tar.gz / -win.zip) instead of the source
    # tarball. The desktop client sends ?kind=bundle&platform=mac|win|linux and
    # follows the redirect to the asset's download URL. (Frozen builds have no .py
    # on disk, so they swap the whole onedir — see the desktop repo's
    # update_service._download_and_stage_bundle.)
    if request.args.get('kind') == 'bundle':
        platform = (request.args.get('platform') or '').strip().lower()
        if platform not in ('mac', 'win', 'linux'):
            return jsonify({'status': 'error', 'message': 'Invalid or missing platform'}), 400
        asset = get_bundle_asset(platform, version_tag)
        if not asset:
            return jsonify({'status': 'error',
                            'message': f'No {platform} bundle published for release {version_tag}'}), 404
        # Redirect to a presigned object-store URL rather than the asset's
        # browser_download_url: the latter 404s for a PRIVATE repo (the client
        # carries only its EasyOKAPI activation token, not a GitHub credential).
        try:
            location = resolve_asset_location(asset)
        except Exception as e:
            print(f'[download] bundle resolve failed for {platform} tag={version_tag!r}: {e}')
            return jsonify({'status': 'error', 'message': 'Failed to resolve bundle download URL'}), 502
        if not location:
            return jsonify({'status': 'error',
                            'message': f'Could not resolve {platform} bundle download URL'}), 502
        user.last_download = datetime.utcnow()
        db.session.commit()
        return redirect(location, code=302)

    # Past this point the endpoint streams the private SOURCE tarball. Only the
    # installer (short-lived download token) is entitled to it. Refuse the source
    # to a frozen-build auto-updater (Bearer activation token) — it can only ever
    # fetch the compiled bundle above — so the source is never leaked down the
    # update path, even to a valid license on a machine that should run a binary.
    if via_activation:
        return jsonify({'status': 'error', 'code': 'source_forbidden',
                        'message': 'This credential can only fetch the update bundle '
                                   '(use ?kind=bundle&platform=mac|win|linux).'}), 403

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
