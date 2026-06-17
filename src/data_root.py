"""User-selectable data-root location (frozen builds).

The writable data root (``state.script_dir``) holds every user artifact: the
``data/``, ``json/``, ``report/`` and ``log/`` trees plus ``user_settings.json``,
``activation.json``, ``ai_settings.json``, ``.env`` and first-run markers. By
default it lives at ``<Documents>/EasyOKAPI`` (win/mac) or ``~/EasyOKAPI``
(linux); this module lets the user relocate it.

The location can't be stored in ``user_settings.json`` (that file lives *inside*
the data root — chicken-and-egg), so it is recorded in a tiny ``.dataroot``
pointer file kept at the DEFAULT location (``state.default_data_root``).
``state._read_dataroot_override()`` reads it on startup. Because the override is
resolved at import time, changing it requires an app restart to take effect.

Source/dev runs always use the project root and ignore the pointer, so these
functions are no-ops there beyond reporting the current root.
"""

import os
import shutil

import state

# Everything that lives directly under the data root and must travel with it.
_DATA_DIRS = ("data", "json", "report", "log")
_DATA_FILES = (
    "user_settings.json",
    "activation.json",
    "ai_settings.json",
    ".env",
    ".demo_prompt_done",
    ".migrated_appdata",
)


def get_info() -> dict:
    """Current data root, the default location, and whether it's been moved."""
    current = os.path.abspath(state.script_dir)
    default = os.path.abspath(state.default_data_root)
    return {
        "current": current,
        "default": default,
        "is_custom": current != default,
    }


def _normalize(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path.strip())))


def _assert_writable(path: str) -> None:
    """Raise ValueError unless we can create/write inside ``path``."""
    probe_dir = path if os.path.isdir(path) else os.path.dirname(path) or path
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".dataroot_write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError:
        raise ValueError(f"The folder is not writable: {probe_dir}")


def _validate(new_path: str) -> str:
    if not new_path or not new_path.strip():
        raise ValueError("A data folder path is required.")
    target = _normalize(new_path)
    if not os.path.isabs(target):
        raise ValueError("The data folder must be an absolute path.")
    if os.path.exists(target) and not os.path.isdir(target):
        raise ValueError("A file already exists at that path; choose a folder.")
    bundle = os.path.abspath(state.bundle_dir)
    if target == bundle or target.startswith(bundle + os.sep):
        raise ValueError("The data folder cannot be inside the application files.")
    current = os.path.abspath(state.script_dir)
    if target == current:
        raise ValueError("That is already the current data folder.")
    # Refuse a target nested inside the current root (moving a dir into itself).
    if target.startswith(current + os.sep):
        raise ValueError("The data folder cannot be inside the current data folder.")
    _assert_writable(target)
    return target


def _move_merge(src_root: str, dst_root: str) -> None:
    """Move every data artifact from ``src_root`` into ``dst_root``.

    Never clobbers an item already present at the destination (mirrors the merge
    style in state._migrate_legacy_app_data). Raises on failure, leaving the
    source intact so a half-move can't lose data.
    """
    os.makedirs(dst_root, exist_ok=True)
    for name in _DATA_DIRS:
        src = os.path.join(src_root, name)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(dst_root, name)
        # Merge into an existing destination tree without overwriting files.
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)
    for name in _DATA_FILES:
        src = os.path.join(src_root, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dst_root, name)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        os.remove(src)


def _write_pointer(target: str) -> None:
    """Point the default location's ``.dataroot`` at ``target`` (or clear it)."""
    pointer = os.path.join(state.default_data_root, state._DATAROOT_POINTER)
    default = os.path.abspath(state.default_data_root)
    if os.path.abspath(target) == default:
        if os.path.isfile(pointer):
            os.remove(pointer)
        return
    os.makedirs(state.default_data_root, exist_ok=True)
    with open(pointer, "w", encoding="utf-8") as f:
        f.write(target)


def set_data_root(new_path: str) -> str:
    """Relocate the data root to ``new_path``: validate, move data, write pointer.

    Returns the new absolute path. Raises ValueError on a bad/unwritable path.
    The change takes effect on the next launch (the root is resolved at import).
    """
    target = _validate(new_path)
    _move_merge(state.script_dir, target)
    _write_pointer(target)
    return target


def reset_to_default() -> str:
    """Move the data back to the default location and remove the pointer."""
    return set_data_root(state.default_data_root)
