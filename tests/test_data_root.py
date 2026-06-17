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
        assert data_root.get_info()["is_custom"] is True


# ---------------------------------------------------------------------------
# set_data_root: copy into <parent>/EasyOKAPI + pointer
# ---------------------------------------------------------------------------

class TestSetDataRoot:
    def test_target_is_easyokapi_subfolder_of_chosen(self, tmp_path, monkeypatch):
        _setup_roots(tmp_path, monkeypatch)
        parent = tmp_path / "BigDrive"
        parent.mkdir()
        target = data_root.set_data_root(str(parent))
        assert target == str(parent / "EasyOKAPI")

    def test_writes_pointer_and_state_reads_it_back(self, tmp_path, monkeypatch):
        _setup_roots(tmp_path, monkeypatch)
        parent = tmp_path / "BigDrive"
        target = data_root.set_data_root(str(parent))
        pointer = state._dataroot_pointer_path()
        # pointer lives BESIDE the default folder, not inside it
        assert os.path.dirname(pointer) == os.path.dirname(str(tmp_path / "default_root"))
        assert os.path.isfile(pointer)
        with open(pointer, encoding="utf-8") as f:
            assert f.read().strip() == target
        assert os.path.abspath(state._read_dataroot_override()) == os.path.abspath(target)

    def test_copies_data_and_keeps_original(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        _seed_data(default)
        parent = tmp_path / "BigDrive"
        target = data_root.set_data_root(str(parent))
        # copied to new root
        assert os.path.isfile(os.path.join(target, "data", "exp1.csv"))
        assert os.path.isfile(os.path.join(target, "json", "kinetics", "cal.json"))
        assert os.path.isfile(os.path.join(target, "user_settings.json"))
        # original is left untouched (copy, not move)
        assert (default / "data" / "exp1.csv").is_file()
        assert (default / "user_settings.json").is_file()

    def test_pointer_survives_default_folder_deletion(self, tmp_path, monkeypatch):
        import shutil as _sh
        default, _ = _setup_roots(tmp_path, monkeypatch)
        target = data_root.set_data_root(str(tmp_path / "BigDrive"))
        # user deletes the (now-stale) default folder entirely
        _sh.rmtree(default)
        # pointer is a sibling → override still resolves to the relocated data
        assert os.path.abspath(state._read_dataroot_override()) == os.path.abspath(target)

    def test_does_not_copy_pointer_or_update_artifacts(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        _seed_data(default)
        (default / "_update_download.tar.gz").write_text("x", encoding="utf-8")
        # simulate a stray pointer inside the root (should never be copied)
        (default / state._DATAROOT_POINTER).write_text("/somewhere", encoding="utf-8")
        target = data_root.set_data_root(str(tmp_path / "BigDrive"))
        assert not os.path.exists(os.path.join(target, "_update_download.tar.gz"))
        assert not os.path.exists(os.path.join(target, state._DATAROOT_POINTER))

    def test_reset_to_default_copies_back_and_clears_pointer(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        custom = tmp_path / "BigDrive" / "EasyOKAPI"
        custom.mkdir(parents=True)
        (custom / "data").mkdir()
        (custom / "data" / "new.csv").write_text("x", encoding="utf-8")
        # pretend we are running from the custom root
        monkeypatch.setattr(state, "script_dir", str(custom))
        # write a stale pointer so reset has something to clear
        pointer = state._dataroot_pointer_path()
        with open(pointer, "w", encoding="utf-8") as f:
            f.write(str(custom))
        target = data_root.reset_to_default()
        assert target == str(default)
        assert (default / "data" / "new.csv").is_file()  # copied back
        assert not os.path.exists(pointer)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_rejects_empty(self, tmp_path, monkeypatch):
        _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root("   ")

    def test_rejects_inside_bundle(self, tmp_path, monkeypatch):
        _default, bundle = _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root(str(bundle / "sub"))

    def test_rejects_container_inside_current(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root(str(default / "child"))

    def test_rejects_container_equal_to_current(self, tmp_path, monkeypatch):
        default, _ = _setup_roots(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            data_root.set_data_root(str(default))

    def test_rejects_when_target_equals_current(self, tmp_path, monkeypatch):
        # current root is already <parent>/EasyOKAPI → choosing <parent> is a no-op
        default, _ = _setup_roots(tmp_path, monkeypatch)
        parent = tmp_path / "BigDrive"
        custom = parent / "EasyOKAPI"
        custom.mkdir(parents=True)
        monkeypatch.setattr(state, "script_dir", str(custom))
        with pytest.raises(ValueError):
            data_root.set_data_root(str(parent))

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
        monkeypatch.setattr(state, "IS_FROZEN", False)
        resp = client.post('/data_root', json={"path": "/tmp/whatever"})
        assert resp.status_code == 400

    def test_post_missing_path(self, client, monkeypatch):
        monkeypatch.setattr(state, "IS_FROZEN", True)
        resp = client.post('/data_root', json={})
        assert resp.status_code == 400

    def test_browse_dirs_lists_subfolders(self, client, tmp_path):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "afile.txt").write_text("x", encoding="utf-8")
        resp = client.get('/browse_dirs?path=' + str(tmp_path))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        names = sorted(d["name"] for d in body["dirs"])
        assert names == ["alpha", "beta"]  # files excluded
        assert body["path"] == str(tmp_path)

    def test_browse_dirs_bad_path(self, client):
        resp = client.get('/browse_dirs?path=/no/such/dir/xyz123')
        assert resp.status_code == 400
