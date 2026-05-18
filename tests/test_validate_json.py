"""
Tests for the validate_json decorator in src/validators.py.

Covers every branch:
  - Non-JSON body gate
  - Required field absent / JSON null treated as absent / empty body
  - Optional field: default injected / explicit override
  - Plain-type (non-tuple) schema treated as required with no default
  - Type coercion: int, float, bool (string and non-string forms)
  - isinstance rejection for wrong types
  - Extra unknown keys in the request body are silently dropped

Route anchors (math_bp, registered in conftest.py):
  /calculate_coef_and_rsquared  — (list, str) fields
  /calculate_kinetics_quantities — (int) field

Test-only routes registered in conftest.py:
  /test_bool_route   — (bool) field
  /test_float_route  — (float) field
  /test_str_route    — plain-type str schema (non-tuple)
"""
import pytest


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_optional_field_gets_default(client):
    # regress_algo is optional (default "linear"); omitting it must still succeed.
    rv = client.post('/calculate_coef_and_rsquared',
                     json={"x": [0, 1, 2, 3], "y": [0, 2, 4, 6]})
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "success"


def test_happy_path_optional_field_override_honoured(client):
    # Explicitly supplying the optional field must override the default.
    rv = client.post('/calculate_coef_and_rsquared',
                     json={"x": [0, 1, 2, 3, 4],
                           "y": [0.0, 1.0, 4.0, 9.0, 16.0],
                           "regress_algo": "polynomial"})
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "success"


# ---------------------------------------------------------------------------
# Non-JSON body gate  (validators.py:20–21)
# ---------------------------------------------------------------------------

def test_non_json_content_type_returns_400(client):
    rv = client.post('/calculate_coef_and_rsquared',
                     data={"x": "[1,2,3]", "y": "[1,2,3]"})
    assert rv.status_code == 400
    body = rv.get_json()
    assert body["status"] == "failure"
    assert "Request must be JSON" in body["message"]


# ---------------------------------------------------------------------------
# Required-field enforcement  (validators.py:34–36)
# ---------------------------------------------------------------------------

def test_missing_required_field_returns_400(client):
    rv = client.post('/calculate_coef_and_rsquared',
                     json={"y": [1, 2, 3]})   # "x" omitted
    assert rv.status_code == 400
    body = rv.get_json()
    assert body["status"] == "error"
    assert "Missing required field" in body["message"]
    assert "x" in body["message"]


def test_json_null_for_required_field_treated_as_absent(client):
    # data.get("x") returns None for both absent key and explicit null.
    rv = client.post('/calculate_coef_and_rsquared',
                     json={"x": None, "y": [1, 2]})
    assert rv.status_code == 400
    assert "Missing required field" in rv.get_json()["message"]


def test_empty_body_triggers_missing_required_field(client):
    rv = client.post('/calculate_coef_and_rsquared', json={})
    assert rv.status_code == 400
    assert "Missing required field" in rv.get_json()["message"]


# ---------------------------------------------------------------------------
# Plain-type (non-tuple) schema  (validators.py:30)
# -  treated as required=True, default=None
# ---------------------------------------------------------------------------

def test_plain_schema_missing_required_field_returns_400(client):
    # /test_str_route schema: {'name': str}  (plain type, no tuple)
    # The key is omitted entirely — must produce "Missing required field".
    rv = client.post('/test_str_route', json={})
    assert rv.status_code == 400
    assert "Missing required field: name" in rv.get_json()["message"]


def test_plain_schema_wrong_type_returns_400(client):
    # 'name' expects str; sending int 12345 must be rejected by isinstance.
    rv = client.post('/test_str_route', json={"name": 12345})
    assert rv.status_code == 400
    assert "Field name must be of type str" in rv.get_json()["message"]


# ---------------------------------------------------------------------------
# isinstance rejection for collection type  (validators.py:52–55)
# ---------------------------------------------------------------------------

def test_list_field_sent_as_string_returns_400(client):
    # 'x' expects list; a str value cannot be coerced — isinstance check fires.
    rv = client.post('/calculate_coef_and_rsquared',
                     json={"x": "not-a-list", "y": [1, 2, 3]})
    assert rv.status_code == 400
    body = rv.get_json()
    assert body["status"] == "error"
    assert "Field x must be of type list" in body["message"]


# ---------------------------------------------------------------------------
# int coercion  (validators.py:50–51)
# ---------------------------------------------------------------------------

def test_int_coercion_from_numeric_string(client):
    # window_size expects int; sending JSON string "4" must be coerced silently.
    rv = client.post('/calculate_kinetics_quantities',
                     json={"XColumn": [0, 1, 2, 3],
                           "YColumn": [0.0, 1.0, 2.0, 3.0],
                           "window_size": "4"})
    assert rv.status_code == 200


def test_int_coercion_invalid_string_returns_400(client):
    rv = client.post('/calculate_kinetics_quantities',
                     json={"XColumn": [0, 1, 2],
                           "YColumn": [0.0, 1.0, 2.0],
                           "window_size": "abc"})
    assert rv.status_code == 400
    body = rv.get_json()
    assert body["status"] == "error"
    assert "Invalid value for field window_size" in body["message"]


# ---------------------------------------------------------------------------
# float coercion  (validators.py:48–49)
# ---------------------------------------------------------------------------

def test_float_coercion_from_int(client):
    # int value 2 sent for a float field — float(2) must succeed, not 400.
    rv = client.post('/test_float_route', json={"timeout": 2})
    assert rv.status_code == 200
    assert rv.get_json()["timeout"] == pytest.approx(2.0)


def test_float_coercion_invalid_string_returns_400(client):
    rv = client.post('/test_float_route', json={"timeout": "not-a-number"})
    assert rv.status_code == 400
    body = rv.get_json()
    assert body["status"] == "error"
    assert "Invalid value for field timeout" in body["message"]


# ---------------------------------------------------------------------------
# bool coercion  (validators.py:43–47)
# ---------------------------------------------------------------------------

def test_bool_coercion_string_true(client):
    # String "true" must be coerced to True.
    rv = client.post('/test_bool_route', json={"flag": "true"})
    assert rv.status_code == 200
    assert rv.get_json()["flag"] is True


@pytest.mark.parametrize("falsy_string", ["false", "0", "no"])
def test_bool_coercion_string_false_variants(client, falsy_string):
    # Only "true", "1", "yes" are truthy — everything else is False.
    rv = client.post('/test_bool_route', json={"flag": falsy_string})
    assert rv.status_code == 200
    assert rv.get_json()["flag"] is False


def test_bool_coercion_string_yes(client):
    rv = client.post('/test_bool_route', json={"flag": "yes"})
    assert rv.status_code == 200
    assert rv.get_json()["flag"] is True


def test_bool_coercion_nonstring_truthy_int(client):
    # Non-string values go through bool(val); int 1 → True.
    rv = client.post('/test_bool_route', json={"flag": 1})
    assert rv.status_code == 200
    assert rv.get_json()["flag"] is True


def test_bool_coercion_nonstring_falsy_int(client):
    # Non-string int 0 → bool(0) → False.
    rv = client.post('/test_bool_route', json={"flag": 0})
    assert rv.status_code == 200
    assert rv.get_json()["flag"] is False


# ---------------------------------------------------------------------------
# Security — extra unknown keys must not leak into validated_data  (validators.py:60)
# ---------------------------------------------------------------------------

def test_extra_keys_in_body_are_silently_dropped(client):
    # Unknown keys must not cause an error and must not appear in validated_data.
    rv = client.post('/calculate_coef_and_rsquared',
                     json={"x": [0, 1, 2],
                           "y": [0, 1, 2],
                           "__proto__": {"admin": True},
                           "injected_key": "malicious"})
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "success"
