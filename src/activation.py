import json
import os

_PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
_ACTIVATION_PATH = os.path.join(_PROJECT_ROOT, 'activation.json')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'https://www.easyokapi.cbbiotec.vn').rstrip('/')

_token_cache = ...  # type: Optional[str]  # sentinel: ... means "not yet loaded"


def load():
    try:
        with open(_ACTIVATION_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def get_license_token():
    global _token_cache
    if _token_cache is ...:
        _token_cache = load().get('license_token') or None
    return _token_cache


def save(license_token):
    global _token_cache
    try:
        with open(_ACTIVATION_PATH, 'w', encoding='utf-8') as f:
            json.dump({'license_token': license_token}, f, indent=2)
        _token_cache = license_token or None
        return True
    except Exception:
        return False
