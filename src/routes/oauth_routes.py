import os
import secrets
import requests as http_requests
from urllib.parse import urlencode
from flask import Blueprint, redirect, request, session

from account import db, User, OAuthConnection

oauth_bp = Blueprint('oauth', __name__)

_GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
_GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
_GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

_GITHUB_AUTH_URL = 'https://github.com/login/oauth/authorize'
_GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
_GITHUB_USER_URL = 'https://api.github.com/user'
_GITHUB_EMAIL_URL = 'https://api.github.com/user/emails'


def _base_url():
    return os.environ.get('APP_BASE_URL', 'http://localhost:5003').rstrip('/')


def _login_user(user):
    session.permanent = True
    session['account_user_id'] = user.id
    session['account_user_name'] = user.name
    session['account_user_email'] = user.email
    try:
        from user_data import user_data_session
        with user_data_session() as ud:
            ud['drive'] = {
                'mode': 'guest', 'authenticated': False,
                'folder_id': None, 'folder_name': None,
                'credentials': None, 'last_sync': None,
                'auto_sync_on_close': False, 'file_mapping': {},
                'pending_oauth_state': None,
            }
    except Exception as e:
        print(f'[oauth] Drive reset failed (non-fatal): {e}')


def _find_or_create_user(provider, provider_user_id, email, name):
    """Return an existing or new User, ensuring an OAuthConnection exists.
    Raises ValueError with a user-facing message on unrecoverable input problems."""
    conn = OAuthConnection.query.filter_by(
        provider=provider, provider_user_id=str(provider_user_id)
    ).first()
    if conn:
        return conn.user

    if not email:
        raise ValueError(
            f'Your {provider.title()} account has no verified email. '
            'Please add one or use email/password sign-up instead.'
        )

    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name=name or email.split('@')[0])
        user.set_password(secrets.token_hex(32))
        user.is_verified = True
        db.session.add(user)
        db.session.flush()
    elif not user.is_verified:
        user.is_verified = True

    conn = OAuthConnection(
        user_id=user.id,
        provider=provider,
        provider_user_id=str(provider_user_id),
    )
    db.session.add(conn)
    db.session.commit()
    return user


# ── Google ───────────────────────────────────────────────────────────────────

@oauth_bp.route('/auth/oauth/google')
def oauth_google_start():
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    if not client_id:
        return redirect('/account/login?oauth_error=Google+sign-in+is+not+configured')

    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['oauth_provider'] = 'google'

    params = {
        'client_id': client_id,
        'redirect_uri': f'{_base_url()}/auth/oauth/google/callback',
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
    }
    return redirect(f'{_GOOGLE_AUTH_URL}?{urlencode(params)}')


@oauth_bp.route('/auth/oauth/google/callback')
def oauth_google_callback():
    if request.args.get('error'):
        return redirect('/account/login?oauth_error=Google+sign-in+was+cancelled')

    if request.args.get('state') != session.pop('oauth_state', None):
        return redirect('/account/login?oauth_error=Invalid+state+parameter')

    code = request.args.get('code')
    token_resp = http_requests.post(_GOOGLE_TOKEN_URL, data={
        'code': code,
        'client_id': os.environ.get('GOOGLE_OAUTH_CLIENT_ID'),
        'client_secret': os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET'),
        'redirect_uri': f'{_base_url()}/auth/oauth/google/callback',
        'grant_type': 'authorization_code',
    }, timeout=10)
    if not token_resp.ok:
        return redirect('/account/login?oauth_error=Google+authentication+failed')

    access_token = token_resp.json().get('access_token')
    info_resp = http_requests.get(_GOOGLE_USERINFO_URL, headers={
        'Authorization': f'Bearer {access_token}'
    }, timeout=10)
    if not info_resp.ok:
        return redirect('/account/login?oauth_error=Could+not+fetch+Google+profile')

    info = info_resp.json()
    try:
        user = _find_or_create_user(
            'google',
            info.get('id'),
            info.get('email'),
            info.get('name') or info.get('given_name', ''),
        )
    except ValueError as exc:
        return redirect(f'/account/login?oauth_error={exc}')
    except Exception as exc:
        print(f'[oauth/google] {exc}')
        return redirect('/account/login?oauth_error=Sign-in+failed.+Please+try+again.')

    _login_user(user)
    return redirect('/')


# ── GitHub ───────────────────────────────────────────────────────────────────

@oauth_bp.route('/auth/oauth/github')
def oauth_github_start():
    client_id = os.environ.get('GITHUB_OAUTH_CLIENT_ID')
    if not client_id:
        return redirect('/account/login?oauth_error=GitHub+sign-in+is+not+configured')

    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['oauth_provider'] = 'github'

    params = {
        'client_id': client_id,
        'redirect_uri': f'{_base_url()}/auth/oauth/github/callback',
        'scope': 'read:user user:email',
        'state': state,
    }
    return redirect(f'{_GITHUB_AUTH_URL}?{urlencode(params)}')


@oauth_bp.route('/auth/oauth/github/callback')
def oauth_github_callback():
    if request.args.get('error'):
        return redirect('/account/login?oauth_error=GitHub+sign-in+was+cancelled')

    if request.args.get('state') != session.pop('oauth_state', None):
        return redirect('/account/login?oauth_error=Invalid+state+parameter')

    code = request.args.get('code')
    token_resp = http_requests.post(_GITHUB_TOKEN_URL, data={
        'client_id': os.environ.get('GITHUB_OAUTH_CLIENT_ID'),
        'client_secret': os.environ.get('GITHUB_OAUTH_CLIENT_SECRET'),
        'code': code,
        'redirect_uri': f'{_base_url()}/auth/oauth/github/callback',
    }, headers={'Accept': 'application/json'}, timeout=10)
    if not token_resp.ok:
        return redirect('/account/login?oauth_error=GitHub+authentication+failed')

    access_token = token_resp.json().get('access_token')
    auth_headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }

    user_resp = http_requests.get(_GITHUB_USER_URL, headers=auth_headers, timeout=10)
    if not user_resp.ok:
        return redirect('/account/login?oauth_error=Could+not+fetch+GitHub+profile')

    gh = user_resp.json()
    email = gh.get('email')
    if not email:
        emails_resp = http_requests.get(_GITHUB_EMAIL_URL, headers=auth_headers, timeout=10)
        if emails_resp.ok:
            for entry in emails_resp.json():
                if entry.get('primary') and entry.get('verified'):
                    email = entry['email']
                    break

    try:
        user = _find_or_create_user(
            'github',
            gh.get('id'),
            email,
            gh.get('name') or gh.get('login', ''),
        )
    except ValueError as exc:
        return redirect(f'/account/login?oauth_error={exc}')
    except Exception as exc:
        print(f'[oauth/github] {exc}')
        return redirect('/account/login?oauth_error=Sign-in+failed.+Please+try+again.')

    _login_user(user)
    return redirect('/')
