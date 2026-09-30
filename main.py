from flask import Flask, render_template, request, jsonify, make_response, redirect, session
import os
import sys
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix

# Add src to path
sys.path.append('src')
from user_data import init_user_data
from range import get_range_input
from mode import get_mode_input
from quantity import get_quantity_input
from file_path import (CONCEN_UNITS, build_csv_identity_from_store,
                       build_json_identity_from_store)
from config import Config
from extensions import socketio

# Import Blueprints
from routes.auth_routes import auth_bp
from routes.file_routes import file_bp
from routes.data_routes import data_bp
from routes.math_routes import math_bp
from routes.ai_routes import ai_bp
from routes.account_routes import account_bp
from download_service import get_release, get_release_asset, _RELEASE_ASSET_SUFFIX, resolve_asset_location
from routes.oauth_routes import oauth_bp
from routes.community_routes import community_bp
from routes.contact_routes import contact_bp
import community
import contact as contact_form
import i18n
from account import db, run_migrations

app = Flask(__name__, static_folder='static')
app.config.from_object(Config)

# Production Security & Session handling
if not app.debug:
    # Use ProxyFix to handle HTTPS behind Heroku's proxy
    # x_for=1 so the rate limiter keys on the real client, not the router.
    from rate_limit import PROXY_FIX_KWARGS
    app.wsgi_app = ProxyFix(app.wsgi_app, **PROXY_FIX_KWARGS)
    # Ensure cookies are sent over HTTPS and during OAuth redirects
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_HTTPONLY'] = True

# Initialize SocketIO and SQLAlchemy with app
socketio.init_app(app)
db.init_app(app)

# Rate limiting (abuse / cost-drain protection on the AI + activation endpoints).
# Storage is Redis when REDIS_URL is set so limits hold across dynos; in-memory
# otherwise. Decorators live on the routes (see routes/ai_routes.py).
from rate_limit import limiter
limiter.init_app(app)

# Cross-origin/CSRF defense-in-depth: reject state-changing browser requests
# whose Origin isn't ours. Registered first so it runs before any session or
# idle-timeout logic. Token-authenticated desktop calls send no Origin and are
# unaffected. See src/security.py.
from security import init_request_guard
init_request_guard(app)

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
app.register_blueprint(community_bp)
app.register_blueprint(contact_bp)

delimiter = "/"

# ── Account inactivity auto-logout ───────────────────────────────────────────
# Logs an account out once the EasyOKAPI tab has been left unopened (hidden or
# closed) for longer than Config.ACCOUNT_IDLE_TIMEOUT. The web app
# (templates/index.html, served at /webapp) sends a heartbeat to
# /api/account/heartbeat only while its tab is visible, and opening the app page
# counts as activity; those are the only paths that refresh `last_activity`. The
# landing page at / does not — a visitor reading it is not using the app. Every
# other request merely checks the stamp, so a backgrounded tab's polling
# (e.g. /ping every few seconds) cannot keep the session alive.
_ACTIVITY_REFRESH_PATHS = {'/webapp', '/api/account/heartbeat'}


@app.before_request
def enforce_account_idle_timeout():
    account_id = session.get('account_user_id')
    if not account_id:
        return

    # Drop the session immediately if this account was banned mid-session, so a
    # ban takes effect on the user's open tab on their very next request — not
    # only at their next fresh login.
    from account import User
    banned_user = User.query.get(account_id)
    if banned_user is not None and banned_user.banned:
        for key in ('account_user_id', 'account_user_name', 'account_user_email', 'last_activity'):
            session.pop(key, None)
        if request.path.startswith('/api/'):
            return jsonify({'status': 'error', 'code': 'account_banned',
                            'message': 'This account has been suspended.'}), 403
        return

    now = datetime.utcnow()
    last_raw = session.get('last_activity')
    last_dt = None
    if last_raw:
        try:
            last_dt = datetime.fromisoformat(last_raw)
        except (ValueError, TypeError):
            last_dt = None

    if last_dt is not None and (now - last_dt) > app.config['ACCOUNT_IDLE_TIMEOUT']:
        # Idle past the limit — drop the account session.
        for key in ('account_user_id', 'account_user_name', 'account_user_email', 'last_activity'):
            session.pop(key, None)
        if request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'code': 'session_expired',
                'message': 'You were logged out after a period of inactivity. Please log in again.'
            }), 401
        # Page navigations fall through and simply render in the logged-out state.
        return

    # Still within the window. Refresh the stamp only on genuine activity signals
    # (first request after login, the main page load, or an explicit heartbeat).
    if last_dt is None or request.path in _ACTIVITY_REFRESH_PATHS:
        session['last_activity'] = now.isoformat()
        session.permanent = True

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
def landing():
    """Product landing page.

    Purely informational: it opens no user session storage and refreshes no
    activity stamp, so a visitor who never enters the app costs nothing. The app
    itself lives at /webapp (see `index` below).
    """
    # A visitor who last read the site in another language is sent to that
    # language's landing page. Keyed on the cookie alone — never on
    # Accept-Language — so a crawler, which sends no cookie, always gets the
    # canonical English page at `/`. Picking English in the switcher writes
    # en to the cookie first, so it is still reachable.
    remembered = request.cookies.get(i18n.LANG_COOKIE)
    if i18n.current_lang() == i18n.DEFAULT_UI_LANG and \
            remembered in i18n.PREFIXED_LANGUAGES:
        response = redirect(i18n.url_for_lang(remembered))
        response.headers['Vary'] = 'Cookie'
        return response

    account_user = None
    if session.get('account_user_id'):
        account_user = {
            'id': session['account_user_id'],
            'name': session.get('account_user_name', ''),
            'email': session.get('account_user_email', '')
        }

    return render_template('landing.html',
                           title="Easy OKAPI — Open-colorimeter Kinetics Analysis Platform",
                           testimonials=community.get_testimonials(),
                           publication_ref=community.get_publications(),
                           org_ref=community.get_organizations(),
                           download_available=DOWNLOAD_AVAILABLE,
                           year=datetime.utcnow().year,
                           account_user=account_user)


# ── Legal pages ───────────────────────────────────────────────────────────────
# Terms and Privacy are static prose, so they take no session and refresh no
# activity stamp — same contract as the landing page. Bump LEGAL_VERSION and
# LEGAL_EFFECTIVE together whenever the text of either document changes; the two
# values are what a user (or a store reviewer) cites when identifying a version.
LEGAL_VERSION = '1.0'
LEGAL_EFFECTIVE = '3 August 2026'

# The one address every legal page, the contact page and the footer point at.
CONTACT_EMAIL = 'tqmthong@gmail.com'

# The accessibility statement is versioned separately from the Terms: it is
# revised when the conformance claim changes (a limitation fixed or found, a
# fresh assessment), not when a commercial clause does.
A11Y_VERSION = '1.0'
A11Y_EFFECTIVE = '11 August 2026'


@app.route('/terms')
def terms():
    # Page copy is looked up from the catalog by key (see src/i18n.py), so the
    # <title> and meta description are translated too — they are what a search
    # result shows, and an English snippet under a Vietnamese URL helps nobody.
    return render_template('terms.html',
                           title_key='terms.page_title',
                           meta_description_key='terms.meta_description',
                           eyebrow_key='legal.eyebrow',
                           effective_date=LEGAL_EFFECTIVE,
                           doc_version=LEGAL_VERSION,
                           contact_email=CONTACT_EMAIL,
                           year=datetime.utcnow().year)


@app.route('/privacy')
def privacy():
    return render_template('privacy.html',
                           title_key='privacy.page_title',
                           meta_description_key='privacy.meta_description',
                           eyebrow_key='legal.eyebrow',
                           effective_date=LEGAL_EFFECTIVE,
                           doc_version=LEGAL_VERSION,
                           contact_email=CONTACT_EMAIL,
                           year=datetime.utcnow().year)


@app.route('/accessibility')
def accessibility():
    """The published accessibility statement (WCAG 2.2 AA conformance claim).

    Rendered on the same legal frame as the Terms and the Privacy Policy, and
    carries the same version/effective-date readout: a conformance claim is
    dated, because it describes the software as it was assessed. Its own
    version moves when the *claim* changes (a new limitation, a new assessment,
    a different target), which is not the same event as a Terms revision —
    hence the separate constants.
    """
    return render_template('accessibility.html',
                           title_key='a11y.page_title',
                           meta_description_key='a11y.meta_description',
                           eyebrow_key='a11y.eyebrow',
                           effective_date=A11Y_EFFECTIVE,
                           doc_version=A11Y_VERSION,
                           contact_email=CONTACT_EMAIL,
                           year=datetime.utcnow().year)


@app.route('/contact')
def contact():
    """The contact form.

    Same no-session contract as the landing and legal pages. The form posts to
    `/api/contact` (see `src/routes/contact_routes.py`), which mails the message
    to the team inbox — this page replaced a `mailto:` link, which was unusable
    for a visitor with no desktop mail client configured.
    """
    return render_template('contact.html',
                           title_key='contact.page_title',
                           meta_description_key='contact.meta_description',
                           eyebrow_key='contact.eyebrow',
                           topics=contact_form.TOPICS,
                           topic_keys=contact_form.TOPIC_KEYS,
                           max_message_len=contact_form.MAX_MESSAGE_LEN,
                           min_message_len=contact_form.MIN_MESSAGE_LEN,
                           contact_email=CONTACT_EMAIL,
                           year=datetime.utcnow().year)


@app.route('/webapp')
def index():
    # Initialize user data storage
    range_input = get_range_input()
    mode_input = get_mode_input()
    quantity_input = get_quantity_input()
    user_data = init_user_data()
    file_list = list(user_data['csv'].keys())
    cal_json_list = list(user_data['json'].get('kinetics', {}).keys())
    # Per-file identity (Measurement/Unit/ConcenUnit) for the identity badge.
    file_identity = build_csv_identity_from_store(user_data['csv'])
    cal_json_identity = build_json_identity_from_store(user_data['json'].get('kinetics', {}))

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
                         file_identity=file_identity,
                         cal_json_list=cal_json_list,
                         cal_json_identity=cal_json_identity,
                         concen_units=CONCEN_UNITS,
                         # Reviews, the citation block and the installer buttons
                         # are the landing page's job now, so none of the curated
                         # community content or DOWNLOAD_AVAILABLE is needed here.
                         delimiter=delimiter,
                         production_mode= app.config['PRODUCTION_MODE'],
                         account_user=account_user))
    return response

# ------------------------------------------------------------------
# GitHub Release Downloads
# Installers are served from the repo's latest published GitHub Release.
# Release cache + _RELEASE_ASSET_SUFFIX live in download_service.py.
# ------------------------------------------------------------------

# Manual master switch for offline-build availability. Set a platform to False to
# mark its build "Work in progress": the UI button is disabled and /download/<p>
# refuses to serve. Keys must match _RELEASE_ASSET_SUFFIX ('mac', 'win', 'linux').
DOWNLOAD_AVAILABLE = {'mac': False, 'win': True, 'linux': False}

@app.route('/api/release-info')
def api_release_info():
    try:
        release = get_release()
        version = (release.get('tag_name') if release else None) or 'unknown'  # e.g. "v1.1.4"
        available = {
            p: DOWNLOAD_AVAILABLE.get(p, False) and get_release_asset(p) is not None
            for p in _RELEASE_ASSET_SUFFIX
        }
        return jsonify({'version': version, 'available': available})
    except Exception as e:
        return jsonify({'error': str(e), 'version': None, 'available': {}}), 502

@app.route('/download/<platform>')
def download_offline(platform):
    if platform not in _RELEASE_ASSET_SUFFIX:
        return jsonify({'status': 'error', 'message': 'Unknown platform'}), 404
    if not DOWNLOAD_AVAILABLE.get(platform, False):
        return jsonify({'status': 'error', 'message': f'The {platform} build is a work in progress'}), 403
    try:
        asset = get_release_asset(platform)
        if not asset:
            return jsonify({'status': 'error', 'message': f'No {platform} build available yet'}), 404
        # Ask GitHub for the presigned object-store URL (works for private repos too).
        location = resolve_asset_location(asset)
        if not location:
            return jsonify({'status': 'error', 'message': 'Could not resolve download URL'}), 502
        return redirect(location)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 502

@app.route("/api/current_output", methods=["GET"])
def api_current_output():
    return jsonify({"exists": False, "message": "Not supported in multiuser mode"}), 404


# ── UI localization ───────────────────────────────────────────────────────────
# Installed last, because it mirrors the already-registered page rules under a
# /<lang>/ prefix (English keeps the bare, canonical path). See src/i18n.py.
i18n.init_app(app)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    host = '0.0.0.0'
    try:
        socketio.run(app, debug=False, host=host, port=port)
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        sys.exit(1)