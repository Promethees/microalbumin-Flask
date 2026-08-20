import os
import secrets
import requests as http_requests
from urllib.parse import urlencode, quote_plus
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
    """The host this sign-in actually started on, when we serve it.

    Both uses per provider — the authorize redirect and the token exchange — must
    send the *same* redirect_uri, and the callback lands on the host the user was
    already on, so they agree by construction. See security.request_base_url for
    why this is allowlisted rather than taken from the Host header.

    Google sign-in and Drive use this. GitHub does not — see _github_base_url.
    """
    from security import request_base_url
    return request_base_url().rstrip('/')


def _github_base_url():
    """The ONE host GitHub sign-in is registered against, whatever host we are on.

    GitHub's OAuth app holds a single authorisation callback URL, so unlike
    Google there is no second host to register the fallback against. The
    redirect_uri therefore stays pinned to the branded domain
    (``GITHUB_OAUTH_BASE_URL``, defaulting to ``APP_BASE_URL``) rather than
    following the request.

    Which means a GitHub sign-in **cannot** be started from any other host, and
    not merely because that host might be down: ``oauth_state`` is stashed in the
    session cookie, cookies are host-scoped, and the callback would land on the
    branded host with a different cookie jar — so the state check fails and the
    user is bounced to "Invalid state parameter" even when everything is up.
    oauth_github_start() refuses the flow up front instead of sending someone
    through GitHub to a guaranteed dead end.
    """
    return (os.environ.get('GITHUB_OAUTH_BASE_URL')
            or os.environ.get('APP_BASE_URL', 'http://localhost:5003')).rstrip('/')


def github_signin_available():
    """True when GitHub sign-in can actually complete from the current host.

    The login and sign-up pages ask this so the button is only offered where it
    works — a visible control that always fails is worse than an absent one.
    """
    try:
        from security import request_base_url
        return request_base_url().rstrip('/') == _github_base_url()
    except Exception:
        return True


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
    # Only trust the email if Google says it verified ownership. Google can
    # return verified_email=false (unverified custom-domain / legacy accounts);
    # linking on an unverified address would let a stranger's Google account take
    # over an existing password account that happens to share the email string.
    if info.get('email') and not info.get('verified_email'):
        return redirect('/account/login?oauth_error=Your+Google+email+is+not+verified.+'
                        'Please+verify+it+with+Google+or+use+email/password+sign-in.')
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
    return redirect('/webapp')


# ── GitHub ───────────────────────────────────────────────────────────────────

@oauth_bp.route('/auth/oauth/github')
def oauth_github_start():
    client_id = os.environ.get('GITHUB_OAUTH_CLIENT_ID')
    if not client_id:
        return redirect('/account/login?oauth_error=GitHub+sign-in+is+not+configured')

    # Starting here would send the user to GitHub and then to a callback on a
    # different host, where their oauth_state cookie does not exist — a
    # guaranteed "Invalid state parameter" at the end of a round trip. Say so
    # now, and name the host that does work.
    if not github_signin_available():
        msg = quote_plus(
            'GitHub sign-in is only available at %s. Use Google or your e-mail '
            'address to sign in here.' % _github_base_url())
        return redirect('/account/login?oauth_error=' + msg)

    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['oauth_provider'] = 'github'

    params = {
        'client_id': client_id,
        'redirect_uri': f'{_github_base_url()}/auth/oauth/github/callback',
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
        'redirect_uri': f'{_github_base_url()}/auth/oauth/github/callback',
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
    return redirect('/webapp')
