import json
import os

_PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
_ACTIVATION_PATH = os.path.join(_PROJECT_ROOT, 'activation.json')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'https://www.easyokapi.cbbiotec.vn').rstrip('/')


def load():
    try:
        with open(_ACTIVATION_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def get_license_token():
    return load().get('license_token') or None


def save(license_token):
    try:
        with open(_ACTIVATION_PATH, 'w', encoding='utf-8') as f:
            json.dump({'license_token': license_token}, f, indent=2)
        return True
    except Exception:
        return False
