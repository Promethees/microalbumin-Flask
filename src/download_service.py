import os
import time
import jwt
import requests

_DOWNLOAD_PURPOSE = 'app_download'   # short-lived (exp-bearing) download token
_ACTIVATION_PURPOSE = 'activation'   # permanent (no-exp) activation token
# Purposes accepted as a permanent activation credential. 'app_download' is kept
# for backward compatibility: permanent tokens minted before the purpose split
# inherited the download token's purpose. New tokens use _ACTIVATION_PURPOSE.
_ACTIVATION_PURPOSES = frozenset({_ACTIVATION_PURPOSE, _DOWNLOAD_PURPOSE})
_TOKEN_TTL = 30 * 60  # 30 minutes

_GITHUB_REPO = 'Promethees/microalbumin-Flask'


def _gh_headers() -> dict:
    h = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        h['Authorization'] = f'Bearer {token}'
    return h


# ── GitHub Release assets ─────────────────────────────────────────────────────
# Version checks and the public download buttons resolve to the repo's latest
# published GitHub Release and its built installers. No manual configuration is
# needed. Callers may pass an explicit tag to get_release()/get_release_asset()
# to serve a specific Release instead.

# Match a release asset to a platform by its filename suffix.
# (mac → EasyOKAPI_<ver>.dmg, win → EasyOKAPI_Setup_<ver>.exe, linux → *_linux_<ver>.tar.gz)
_RELEASE_ASSET_SUFFIX = {'mac': '.dmg', 'win': '.exe', 'linux': '.tar.gz'}

_release_cache: dict = {'release': None, 'ts': 0.0, 'tag': None}
_RELEASE_CACHE_TTL = 900  # 15 minutes


def get_release(tag: str | None = None) -> dict | None:
    """Fetch and cache a GitHub Release.

    With no tag, resolves to the repo's latest published Release. Pass an explicit
    tag (e.g. 'v1.1.4') to fetch that specific Release. Returns the release JSON
    object, or None when the release does not exist.
    """
    tag = (tag or '').strip()
    now = time.time()
    if (_release_cache['release'] is not None
            and _release_cache['tag'] == tag
            and now - _release_cache['ts'] < _RELEASE_CACHE_TTL):
        return _release_cache['release']
    if tag:
        url = f'https://api.github.com/repos/{_GITHUB_REPO}/releases/tags/{tag}'
    else:
        url = f'https://api.github.com/repos/{_GITHUB_REPO}/releases/latest'
    resp = requests.get(url, headers=_gh_headers(), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    release = resp.json()
    _release_cache.update(release=release, ts=now, tag=tag)
    return release


def get_release_asset(platform: str, tag: str | None = None) -> dict | None:
    """Return the GitHub Release asset dict for a platform, matched by filename suffix.

    Returns None when the platform is unknown, the release is missing, or the
    release has no asset for that platform.
    """
    suffix = _RELEASE_ASSET_SUFFIX.get(platform)
    if not suffix:
        return None
    release = get_release(tag)
    if not release:
        return None
    for asset in release.get('assets', []):
        name = asset.get('name', '').lower()
        # Skip the in-app update *bundle* archives — on Linux they share the
        # '.tar.gz' suffix with the installer and would otherwise shadow it.
        # The public download must always resolve to the installer.
        if 'bundle' in name:
            continue
        if name.endswith(suffix):
            return asset
    return None


# Match the in-app update *bundle* (the PyInstaller onedir archive) per platform.
# CI publishes EasyOKAPI-bundle-{mac,linux}.tar.gz and EasyOKAPI-bundle-win.zip.
_BUNDLE_ASSET_SUFFIX = {
    'mac': 'bundle-mac.tar.gz',
    'win': 'bundle-win.zip',
    'linux': 'bundle-linux.tar.gz',
}


def get_bundle_asset(platform: str, tag: str | None = None) -> dict | None:
    """Return the GitHub Release asset for the no-source onedir *bundle* of a platform.

    This is the artifact the desktop app's in-app binary-swap updater downloads
    (GET /api/download?kind=bundle&platform=...). It is distinct from
    get_release_asset(), which returns the installer (.dmg/.exe/installer .tar.gz).
    Returns None when the platform is unknown, the release is missing, or the
    release has no bundle asset.
    """
    suffix = _BUNDLE_ASSET_SUFFIX.get(platform)
    if not suffix:
        return None
    release = get_release(tag)
    if not release:
        return None
    for asset in release.get('assets', []):
        if asset.get('name', '').lower().endswith(suffix):
            return asset
    return None


def get_latest_release_tag() -> str | None:
    """Return the tag of the latest published GitHub Release (e.g. 'v1.1.4'), or None.

    The tag matches the git tag used in the repo so it can be passed directly to
    fetch_github_release(). Strip the leading 'v' for plain semver comparison.
    """
    try:
        release = get_release()
        return release.get('tag_name') if release else None
    except Exception:
        return None


# ── Token helpers ─────────────────────────────────────────────────────────────
#
# Two token kinds:
#   * download token   — short-lived (30 min), HS256 (SECRET_KEY). Proves account
#                        identity for the duration of a download. Unchanged.
#   * activation token — permanent (no exp), RS256 (ACTIVATION_PRIVATE_KEY) and
#                        bound to one machine via an 'hwid' claim. The desktop
#                        client verifies it OFFLINE with the embedded public key,
#                        so it must be asymmetrically signed — the client must
#                        never hold a secret that could mint tokens.
#
# Backward compatibility: activation tokens issued before hardware locking were
# HS256 with no 'hwid'. validate_activation_token() still accepts those (legacy),
# and issue_activation_token() falls back to HS256 only when no signing key is
# configured, so a half-configured server keeps working (without the hardware
# lock) rather than failing outright.


def _activation_private_key():
    """PEM private key used to sign permanent activation tokens, or None.

    Lives in the ACTIVATION_PRIVATE_KEY env var (never in source). The matching
    public key is embedded in the desktop client (src/activation_pubkey.py).
    """
    return (os.environ.get('ACTIVATION_PRIVATE_KEY') or '').strip() or None


_pubkey_cache = {'pem': None, 'derived': False}


def _activation_public_key():
    """Derive (and cache) the PEM public key from the configured private key."""
    if not _pubkey_cache['derived']:
        priv = _activation_private_key()
        pem = None
        if priv:
            try:
                from cryptography.hazmat.primitives import serialization
                obj = serialization.load_pem_private_key(priv.encode(), password=None)
                pem = obj.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode()
            except Exception as e:
                print(f'[activation] Could not load ACTIVATION_PRIVATE_KEY: {e}')
        _pubkey_cache['pem'] = pem
        _pubkey_cache['derived'] = True
    return _pubkey_cache['pem']


def issue_activation_token(validated_payload: dict, hwid: str = None) -> str:
    """Mint a permanent activation token, hardware-locked to `hwid` when provided.

    RS256-signed with ACTIVATION_PRIVATE_KEY so the desktop client can verify it
    offline. Falls back to legacy HS256 (no hwid) only when no signing key is set.
    """
    # Strip 'exp' — a permanent token never expires, and its ABSENCE is what
    # distinguishes it from a short-lived download token in validate_*.
    payload = {k: v for k, v in validated_payload.items() if k != 'exp'}
    priv = _activation_private_key()
    if priv:
        # RS256 permanent token: stamp the distinct 'activation' purpose so it is
        # unambiguously not a download token. The desktop client verifies RS256
        # by signature (it does not gate on purpose), so this is safe for it.
        payload['purpose'] = _ACTIVATION_PURPOSE
        if hwid:
            payload['hwid'] = hwid
        return jwt.encode(payload, priv, algorithm='RS256')
    # Legacy fallback: no signing key configured → unbound HS256 token. Keep the
    # incoming 'app_download' purpose, because the desktop client's unverifiable-
    # HS256 path requires exactly that purpose; these tokens carry no 'exp', so
    # validate_activation_token still accepts them. Drop any hwid claim, because
    # the client rejects an hwid on an (unverifiable) HS256 token as tampering.
    print('[activation] ACTIVATION_PRIVATE_KEY not set — issuing legacy HS256 token (no hardware lock)')
    payload.pop('hwid', None)
    secret = os.environ.get('SECRET_KEY', 'change-me')
    return jwt.encode(payload, secret, algorithm='HS256')


def _assert_activation_claims(payload: dict) -> dict:
    """Reject anything that is not a *permanent* activation credential.

    Two independent checks, either of which closes the "download token doubles as
    a license" hole:

    * No 'exp'. A permanent activation token never carries one (issue_activation_
      token strips it); a short-lived DOWNLOAD token always does. Since download
      tokens are also HS256/SECRET_KEY-signed with purpose 'app_download', they
      would otherwise pass the HS256 branch below — including *expired* ones,
      because exp is not verified here. Rejecting any 'exp'-bearing token stops a
      (possibly long-expired) download token being replayed as a permanent
      license on /ai/proxy/chat and /api/download.
    * Purpose in the activation allowlist (new 'activation' + legacy 'app_download').
    """
    if 'exp' in payload:
        raise jwt.InvalidTokenError('Short-lived download token cannot be used as an activation token')
    if payload.get('purpose') not in _ACTIVATION_PURPOSES:
        raise jwt.InvalidTokenError('Token not valid for activation')
    return payload


def validate_activation_token(token: str) -> dict:
    """Validate a permanent activation token; return its payload (incl. 'hwid').

    Tries RS256 (embedded-key scheme) first, then legacy HS256. Never verifies exp
    (permanent tokens carry none) but REJECTS any token that has an exp claim — see
    _assert_activation_claims. Raises jwt.InvalidTokenError on any failure.
    """
    pub = _activation_public_key()
    rs_error = None
    if pub:
        try:
            payload = jwt.decode(token, pub, algorithms=['RS256'], options={'verify_exp': False})
            return _assert_activation_claims(payload)
        except jwt.InvalidTokenError as e:
            rs_error = e  # bad RS256 signature/claims → fall through to legacy HS256
    secret = os.environ.get('SECRET_KEY', 'change-me')
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'], options={'verify_exp': False})
    except jwt.InvalidTokenError:
        raise rs_error or jwt.InvalidTokenError('Invalid activation token')
    return _assert_activation_claims(payload)


def generate_download_token(user_id: int, email: str) -> str:
    secret = os.environ.get('SECRET_KEY', 'change-me')
    payload = {
        'sub': str(user_id),
        'email': email,
        'purpose': _DOWNLOAD_PURPOSE,
        'iat': int(time.time()),
        'exp': int(time.time()) + _TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm='HS256')


def validate_download_token(token: str) -> dict:
    """Return payload dict, or raise jwt.InvalidTokenError on failure."""
    secret = os.environ.get('SECRET_KEY', 'change-me')
    payload = jwt.decode(token, secret, algorithms=['HS256'])
    if payload.get('purpose') != _DOWNLOAD_PURPOSE:
        raise jwt.InvalidTokenError('Token not valid for download')
    return payload


def fetch_github_release(version_tag: str):
    """Return a streaming response for the GitHub source tarball at version_tag.

    version_tag should be a git ref such as 'v1.0.11' or a branch/commit SHA.
    Caller is responsible for closing the response.
    """
    github_token = os.environ.get('GITHUB_PAT') or os.environ.get('GITHUB_TOKEN', '')
    owner = os.environ.get('GITHUB_OWNER', 'Promethees')
    repo = os.environ.get('GITHUB_REPO', 'microalbumin-Flask')

    url = f'https://api.github.com/repos/{owner}/{repo}/tarball/{version_tag}'
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'EasyOKAPI-AuthServer',
    }
    if github_token:
        headers['Authorization'] = f'Bearer {github_token}'

    response = requests.get(url, headers=headers, stream=True, timeout=30)
    response.raise_for_status()
    return response
