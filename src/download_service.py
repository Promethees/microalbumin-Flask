import os
import time
import jwt
import requests


_DOWNLOAD_PURPOSE = 'app_download'
_TOKEN_TTL = 30 * 60  # 30 minutes


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
    """
    Returns a streaming requests.Response for the GitHub tarball of version_tag.
    Caller is responsible for closing the response.
    """
    github_token = os.environ.get('GITHUB_PAT', '')
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
