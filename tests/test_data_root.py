import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import state
import data_root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_roots(tmp_path, monkeypatch):
    """Point state at a temp default root and a separate read-only bundle."""
    default = tmp_path / "default_root"
    bundle = tmp_path / "bundle"
    default.mkdir()
    bundle.mkdir()
    monkeypatch.setattr(state, "default_data_root", str(default))
    monkeypatch.setattr(state, "script_dir", str(default))
    monkeypatch.setattr(state, "bundle_dir", str(bundle))
    monkeypatch.setattr(state, "IS_FROZEN", True)
    monkeypatch.setattr(state, "_is_frozen", lambda: True)
    return default, bundle


def _seed_data(root):
    (root / "data").mkdir()
    (root / "data" / "exp1.csv").write_text("# Measurement\n0,1\n", encoding="utf-8")
    (root / "json" / "kinetics").mkdir(parents=True)
    (root / "json" / "kinetics" / "cal.json").write_text("{}", encoding="utf-8")
    (root / "user_settings.json").write_text('{"theme":"dark"}', encoding="utf-8")


# ---------------------------------------------------------------------------
# get_info
# ---------------------------------------------------------------------------

class TestGetInfo:
    def test_default_is_not_custom(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        info = data_root.get_info()
        assert info["current"] == str(default)
        assert info["default"] == str(default)
        assert info["is_custom"] is False

    def test_relocated_is_custom(self, tmp_path, monkeypatch):
        _setup_roots(tmp_path, monkeypatch)
        monkeypatch.setattr(state, "script_dir", str(tmp_path / "elsewhere"))
        info = data_root.get_info()
        assert info["is_custom"] is True


# ---------------------------------------------------------------------------
# set_data_root: pointer + move-merge
# ---------------------------------------------------------------------------

class TestSetDataRoot:
    def test_writes_pointer_and_state_reads_it_back(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        new = tmp_path / "new_root"
        data_root.set_data_root(str(new))
        pointer = default / state._DATAROOT_POINTER
        assert pointer.is_file()
        assert pointer.read_text(encoding="utf-8").strip() == str(new)
        # state resolves the override back to the new path
        assert os.path.abspath(state._read_dataroot_override()) == os.path.abspath(str(new))

    def test_moves_data_to_new_root(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        _seed_data(default)
        new = tmp_path / "new_root"
        data_root.set_data_root(str(new))
        # arrived
        assert (new / "data" / "exp1.csv").is_file()
        assert (new / "json" / "kinetics" / "cal.json").is_file()
        assert (new / "user_settings.json").is_file()
        # gone from source
        assert not (default / "data").exists()
        assert not (default / "user_settings.json").exists()

    def test_does_not_clobber_existing_destination_file(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        _seed_data(default)
        new = tmp_path / "new_root"
        new.mkdir()
        new.joinpath("user_settings.json").write_text('{"theme":"light"}', encoding="utf-8")
        data_root.set_data_root(str(new))
        # destination file is preserved, not overwritten by the source
        assert (new / "user_settings.json").read_text(encoding="utf-8") == '{"theme":"light"}'

    def test_reset_to_default_removes_pointer(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        new = tmp_path / "new_root"
        data_root.set_data_root(str(new))
        # now pretend we are running from the custom root
        monkeypatch.setattr(state, "script_dir", str(new))
        data_root.reset_to_default()
        assert not (default / state._DATAROOT_POINTER).exists()


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_rejects_empty(self, tmp_path, monkeypatch):
        _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root("   ")

    def test_rejects_equal_to_current(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root(str(default))

    def test_rejects_inside_bundle(self, tmp_path, monkeypatch):
        _default, bundle = _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root(str(bundle / "sub"))

    def test_rejects_nested_in_current(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root(str(default / "child"))

    def test_rejects_path_that_is_a_file(self, tmp_path, monkeypatch):
        _setup_roots(tmp_path, monkeypatch)
        f = tmp_path / "afile"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError):
            data_root.set_data_root(str(f))


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_get_data_root_shape(self, client):
        resp = client.get('/data_root')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert "current" in body and "default" in body and "is_custom" in body

    def test_post_rejected_in_source_build(self, client, monkeypatch):
        # Source build: relocation disabled.
        monkeypatch.setattr(state, "IS_FROZEN", False)
        resp = client.post('/data_root', json={"path": "/tmp/whatever"})
        assert resp.status_code == 400

    def test_post_missing_path(self, client, monkeypatch):
        monkeypatch.setattr(state, "IS_FROZEN", True)
        resp = client.post('/data_root', json={})
        assert resp.status_code == 400
