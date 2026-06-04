import os
import time
import jwt
import requests

_DOWNLOAD_PURPOSE = 'app_download'
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

def issue_activation_token(validated_payload: dict) -> str:
    """Re-sign a validated download token without expiry for permanent AI access."""
    secret = os.environ.get('SECRET_KEY', 'change-me')
    payload = {k: v for k, v in validated_payload.items() if k != 'exp'}
    return jwt.encode(payload, secret, algorithm='HS256')


def validate_activation_token(token: str) -> dict:
    """Validate a stored activation token (no expiry check). Raises on bad signature."""
    secret = os.environ.get('SECRET_KEY', 'change-me')
    payload = jwt.decode(token, secret, algorithms=['HS256'], options={'verify_exp': False})
    if payload.get('purpose') != _DOWNLOAD_PURPOSE:
        raise jwt.InvalidTokenError('Token not valid for AI access')
    return payload


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
