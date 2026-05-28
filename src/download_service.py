import os
import time
import jwt
import requests


_DOWNLOAD_PURPOSE = 'app_download'
_TOKEN_TTL = 30 * 60  # 30 minutes

# ── GitHub artifact cache ─────────────────────────────────────────────────────

_GITHUB_REPO     = 'Promethees/microalbumin-Flask'
_GITHUB_WORKFLOW = 'main.yml'
_ARTIFACT_PREFIX = {'mac': 'EasyOKAPI-mac-', 'win': 'EasyOKAPI-win-', 'linux': 'EasyOKAPI-linux-'}

_artifact_cache: dict = {'artifacts': None, 'ts': 0.0}
_ARTIFACT_CACHE_TTL = 900  # 15 minutes


def _gh_headers() -> dict:
    h = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        h['Authorization'] = f'Bearer {token}'
    return h


def get_cached_artifacts() -> list:
    """Fetch and cache artifacts from the latest successful CI run on main."""
    now = time.time()
    if _artifact_cache['artifacts'] is not None and now - _artifact_cache['ts'] < _ARTIFACT_CACHE_TTL:
        return _artifact_cache['artifacts']
    run_resp = requests.get(
        f'https://api.github.com/repos/{_GITHUB_REPO}/actions/workflows/{_GITHUB_WORKFLOW}/runs',
        params={'branch': 'main', 'status': 'success', 'per_page': 1},
        headers=_gh_headers(), timeout=10
    )
    run_resp.raise_for_status()
    runs = run_resp.json().get('workflow_runs', [])
    if not runs:
        return []
    art_resp = requests.get(
        f'https://api.github.com/repos/{_GITHUB_REPO}/actions/runs/{runs[0]["id"]}/artifacts',
        headers=_gh_headers(), timeout=10
    )
    art_resp.raise_for_status()
    artifacts = art_resp.json().get('artifacts', [])
    _artifact_cache['artifacts'] = artifacts
    _artifact_cache['ts'] = now
    return artifacts


def get_latest_version() -> str | None:
    """Return the raw version tag from the latest CI build (e.g. 'v1.0.11'), or None.

    The tag matches the git tag used in the repo so it can be passed directly to
    fetch_github_release().  Strip the leading 'v' when comparing against semver strings.
    """
    try:
        artifacts = get_cached_artifacts()
        for art in artifacts:
            if art.get('expired'):
                continue
            for prefix in _ARTIFACT_PREFIX.values():
                if art['name'].startswith(prefix):
                    return art['name'][len(prefix):]  # e.g. "v1.0.11"
        return None
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
