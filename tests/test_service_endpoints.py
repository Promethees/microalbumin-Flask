"""Multi-endpoint failover for the license/AI/update service (src/activation.py).

One Flask deployment answers on several names: a branded custom domain and the
platform's own hostname. The branded name is a DNS + CDN + TLS layer in front of
the same dyno, and that layer can break on its own — a bad CNAME, a mismatched
certificate, or an unrelated hosting panel parked on the name and answering 404
in HTML — while the app behind it is perfectly healthy. These tests pin the
behaviour that keeps an install working through exactly that:

  * every shipped base is tried, best first, and the winner is remembered;
  * a reply that is not our API (HTML from a parked domain, a CDN error page) is
    NOT mistaken for an answer, even though it is a valid HTTP response;
  * a reply that IS ours ends the search even when it is a 4xx — those are
    verdicts, and failing over past one would turn "your token expired" into
    "the server is down";
  * no base answering is 'offline'/'service_down', never a wrongly-blocked user.
"""
import json
import os

import pytest

import activation


@pytest.fixture
def endpoint_file(tmp_path, monkeypatch):
    path = str(tmp_path / 'service_endpoint.json')
    monkeypatch.setattr(activation, '_ENDPOINT_PATH', path)
    return path


@pytest.fixture
def bases(monkeypatch):
    """Three predictable bases, replacing whatever the build actually ships."""
    monkeypatch.setattr(activation, 'AI_SERVICE_URL', 'https://primary.test')
    monkeypatch.setattr(activation, 'FALLBACK_SERVICE_URLS',
                        ('https://second.test', 'https://third.test'))
    return ['https://primary.test', 'https://second.test', 'https://third.test']


class _Resp:
    """Stand-in for a requests Response. `json_body=None` means "not our API"."""

    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body

    def json(self):
        if self._json is None:
            raise ValueError('not JSON')
        return self._json


def _route(monkeypatch, table, calls=None):
    """Patch requests.post so each base answers per `table` (resp or exception)."""
    def fake_post(url, **_kw):
        base = url.rsplit('/api', 1)[0]
        if calls is not None:
            calls.append(base)
        outcome = table.get(base)
        if outcome is None:
            raise OSError('unreachable')
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    import requests
    monkeypatch.setattr(requests, 'post', fake_post)


# ── the base list ─────────────────────────────────────────────────────────────

def test_bases_are_primary_then_fallbacks(bases, endpoint_file):
    assert activation.service_bases() == bases


def test_bases_are_deduplicated(monkeypatch, endpoint_file):
    monkeypatch.setattr(activation, 'AI_SERVICE_URL', 'https://one.test')
    monkeypatch.setattr(activation, 'FALLBACK_SERVICE_URLS',
                        ('https://one.test', 'https://two.test'))
    assert activation.service_bases() == ['https://one.test', 'https://two.test']


def test_remembered_base_goes_first(bases, endpoint_file):
    with open(endpoint_file, 'w', encoding='utf-8') as f:
        json.dump({'base': 'https://third.test'}, f)
    assert activation.service_bases()[0] == 'https://third.test'
    assert sorted(activation.service_bases()) == sorted(bases)  # nothing lost


def test_unknown_remembered_base_is_ignored(bases, endpoint_file):
    # A stale or hand-edited pointer must not pin the app to a host we do not ship.
    with open(endpoint_file, 'w', encoding='utf-8') as f:
        json.dump({'base': 'https://attacker.test'}, f)
    assert activation.service_bases() == bases


def test_service_base_is_the_best_known_one(bases, endpoint_file):
    assert activation.service_base() == 'https://primary.test'


# ── failover ──────────────────────────────────────────────────────────────────

def test_fails_over_past_a_transport_error(bases, endpoint_file, monkeypatch):
    calls = []
    _route(monkeypatch, {'https://third.test': _Resp(200, {'status': 'active'})}, calls)
    resp, base = activation.service_request('POST', '/api/license/check')
    assert base == 'https://third.test'
    assert resp.json() == {'status': 'active'}
    assert calls == bases  # tried in order, stopped at the first that worked


def test_fails_over_past_a_parked_domain(bases, endpoint_file, monkeypatch):
    # The real failure: the name resolves and answers 404 in HTML, from a host
    # that is not us at all. A status-code-only check would stop right here.
    _route(monkeypatch, {
        'https://primary.test': _Resp(404, None),
        'https://second.test': _Resp(200, None),
        'https://third.test': _Resp(200, {'status': 'active'}),
    })
    resp, base = activation.service_request('POST', '/api/license/check')
    assert base == 'https://third.test'
    assert resp.json() == {'status': 'active'}


def test_does_not_fail_over_past_our_own_4xx(bases, endpoint_file, monkeypatch):
    # A JSON 403 is a verdict from our API. Trying the next base would turn a
    # clear answer into a bogus "everything is down".
    calls = []
    _route(monkeypatch, {
        'https://primary.test': _Resp(403, {'status': 'error', 'code': 'banned'}),
        'https://second.test': _Resp(200, {'status': 'active'}),
        'https://third.test': _Resp(200, {'status': 'active'}),
    }, calls)
    resp, base = activation.service_request('POST', '/api/license/check')
    assert base == 'https://primary.test'
    assert resp.status_code == 403
    assert calls == ['https://primary.test']


def test_nothing_answers_returns_none(bases, endpoint_file, monkeypatch):
    _route(monkeypatch, {})
    assert activation.service_request('POST', '/api/license/check') == (None, None)


def test_no_api_answer_still_returns_the_first_reply(bases, endpoint_file, monkeypatch):
    # Some host replied, just not ours. That status is more use than nothing.
    _route(monkeypatch, {
        'https://second.test': _Resp(503, None),
        'https://third.test': _Resp(500, None),
    })
    resp, base = activation.service_request('POST', '/api/license/check')
    assert (resp.status_code, base) == (503, 'https://second.test')


# ── remembering the winner ────────────────────────────────────────────────────

def test_winning_base_is_remembered_and_tried_first(bases, endpoint_file, monkeypatch):
    _route(monkeypatch, {'https://third.test': _Resp(200, {'status': 'active'})})
    activation.service_request('POST', '/api/license/check')
    assert json.load(open(endpoint_file))['base'] == 'https://third.test'

    calls = []
    _route(monkeypatch, {'https://third.test': _Resp(200, {'status': 'active'})}, calls)
    activation.service_request('POST', '/api/license/check')
    assert calls == ['https://third.test']  # straight there, no wasted attempts


def test_a_failed_sweep_does_not_clobber_the_remembered_base(bases, endpoint_file, monkeypatch):
    with open(endpoint_file, 'w', encoding='utf-8') as f:
        json.dump({'base': 'https://second.test'}, f)
    _route(monkeypatch, {})
    activation.service_request('POST', '/api/license/check')
    assert json.load(open(endpoint_file))['base'] == 'https://second.test'


def test_forget_drops_the_remembered_base(bases, endpoint_file, monkeypatch):
    monkeypatch.setattr(activation, '_ACTIVATION_PATH', endpoint_file + '.act')
    monkeypatch.setattr(activation, '_STATUS_PATH', endpoint_file + '.status')
    with open(endpoint_file, 'w', encoding='utf-8') as f:
        json.dump({'base': 'https://third.test'}, f)
    activation.forget()
    assert not os.path.exists(endpoint_file)


# ── how failover feeds the offline diagnosis ──────────────────────────────────

def test_dns_check_passes_when_any_base_resolves(bases, endpoint_file, monkeypatch):
    def fake_getaddrinfo(host, _port):
        if host != 'third.test':
            raise OSError('NXDOMAIN')
        return [(2, 1, 6, '', ('203.0.113.1', 0))]

    monkeypatch.setattr(activation.socket, 'getaddrinfo', fake_getaddrinfo)
    assert activation._service_host_resolves() is True


def test_dns_check_fails_only_when_no_base_resolves(bases, endpoint_file, monkeypatch):
    def boom(*_a, **_k):
        raise OSError('NXDOMAIN')

    monkeypatch.setattr(activation.socket, 'getaddrinfo', boom)
    assert activation._service_host_resolves() is False


def test_all_bases_parked_reads_as_service_down(bases, endpoint_file, monkeypatch):
    monkeypatch.setattr(activation, 'get_license_token', lambda: 'tok')
    monkeypatch.setattr(activation, 'get_hwid', lambda: 'a' * 64)
    monkeypatch.setattr(activation, '_STATUS_PATH', endpoint_file + '.status')
    _route(monkeypatch, {b: _Resp(404, None) for b in bases})
    assert activation.check_revocation_detailed() == ('offline', 'service_down')


# ── streaming downloads ───────────────────────────────────────────────────────
# A stream cannot switch hosts once the body is flowing, but it does not have to:
# the headers arrive first. Failing over on the status line is what stops an
# update download from depending on some earlier call having warmed the pointer.

class _StreamResp(_Resp):
    def __init__(self, status_code=200, json_body=None):
        super().__init__(status_code, json_body)
        self.closed = False

    def close(self):
        self.closed = True


def _route_get(monkeypatch, table, calls=None):
    def fake_get(url, **_kw):
        base = url.rsplit('/api', 1)[0]
        if calls is not None:
            calls.append(base)
        outcome = table.get(base)
        if outcome is None:
            raise OSError('unreachable')
        return outcome
    import requests
    monkeypatch.setattr(requests, 'get', fake_get)


def test_stream_fails_over_past_a_parked_404(bases, endpoint_file, monkeypatch):
    parked = _StreamResp(404)
    good = _StreamResp(200)
    calls = []
    _route_get(monkeypatch, {'https://primary.test': parked,
                             'https://third.test': good}, calls)
    resp, base = activation.service_stream('/api/download')
    assert (resp, base) == (good, 'https://third.test')
    assert calls == bases
    assert parked.closed is True   # the rejected response is not left dangling


def test_stream_returns_none_when_nothing_serves(bases, endpoint_file, monkeypatch):
    _route_get(monkeypatch, {'https://primary.test': _StreamResp(500)})
    assert activation.service_stream('/api/download') == (None, None)


def test_stream_remembers_the_winner(bases, endpoint_file, monkeypatch):
    _route_get(monkeypatch, {'https://second.test': _StreamResp(200)})
    activation.service_stream('/api/download')
    assert json.load(open(endpoint_file))['base'] == 'https://second.test'


def test_stream_asks_for_a_stream(bases, endpoint_file, monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen.update(kw)
        return _StreamResp(200)

    import requests
    monkeypatch.setattr(requests, 'get', fake_get)
    activation.service_stream('/api/download', headers={'X': '1'})
    assert seen['stream'] is True
    assert seen['headers'] == {'X': '1'}


def test_stream_lets_the_caller_set_the_timeout(bases, endpoint_file, monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen.update(kw)
        return _StreamResp(200)

    import requests
    monkeypatch.setattr(requests, 'get', fake_get)
    activation.service_stream('/api/download', timeout=180)
    assert seen['timeout'] == 180   # a long download is not held to the short default
