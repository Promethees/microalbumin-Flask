"""User-selectable data-root location (frozen builds).

The writable data root (``state.script_dir``) holds every user artifact: the
``data/``, ``json/``, ``report/`` and ``log/`` trees plus ``user_settings.json``,
``activation.json``, ``ai_settings.json``, ``.env`` and first-run markers. By
default it lives at ``<Documents>/EasyOKAPI`` (win/mac) or ``~/EasyOKAPI``
(linux); this module lets the user relocate it from App Settings.

Relocating **copies the whole current data folder into an ``EasyOKAPI``
subfolder of the chosen location** and points the app at that copy — the
original is left in place as-is. So choosing ``/Volumes/Big`` makes the new root
``/Volumes/Big/EasyOKAPI``.

The location can't be stored in ``user_settings.json`` (that file lives *inside*
the data root — chicken-and-egg), so it is recorded in a tiny ``.dataroot``
pointer file kept at the DEFAULT location (``state.default_data_root``).
``state._read_dataroot_override()`` reads it on startup. Because the override is
resolved at import time, changing it requires an app restart to take effect.

Source/dev runs always use the project root and ignore the pointer, so these
functions are only wired up for frozen builds (the route is frozen-gated).
"""

import os
import shutil

import state

# Folder name created inside the user's chosen location to hold the data root.
_ROOT_FOLDER_NAME = "EasyOKAPI"


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
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".dataroot_write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError:
        raise ValueError(f"The folder is not writable: {path}")


def _validate_target(target: str) -> str:
    """Validate a candidate data-root path (the actual new root, not the parent)."""
    target = _normalize(target)
    if not os.path.isabs(target):
        raise ValueError("The folder must be an absolute path.")
    if os.path.exists(target) and not os.path.isdir(target):
        raise ValueError("A file already exists at that path; choose a folder.")
    bundle = os.path.abspath(state.bundle_dir)
    if target == bundle or target.startswith(bundle + os.sep):
        raise ValueError("The folder cannot be inside the application files.")
    current = os.path.abspath(state.script_dir)
    if target == current:
        raise ValueError("That is already the current data folder.")
    # Don't copy a tree into itself.
    if target.startswith(current + os.sep):
        raise ValueError("Choose a folder outside the current data folder.")
    _assert_writable(os.path.dirname(target) or target)
    return target


def _copy_ignore(_dir, names):
    """copytree ignore: skip the pointer file and transient update artifacts."""
    skip = set()
    for n in names:
        if (n == state._DATAROOT_POINTER
                or n == ".dataroot_write_test"
                or n.startswith("_update")):
            skip.add(n)
    return skip


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


def _relocate(target: str) -> str:
    """Validate `target`, copy the whole current root into it, point the app there."""
    target = _validate_target(target)
    # Copy the entire current root tree into the new folder (newest wins on a
    # re-copy into an existing folder). The original is left untouched.
    shutil.copytree(state.script_dir, target, ignore=_copy_ignore, dirs_exist_ok=True)
    _write_pointer(target)
    return target


def set_data_root(parent_dir: str) -> str:
    """Relocate by COPYING the current data root into ``<parent_dir>/EasyOKAPI``.

    The user picks a *container* folder; the data is copied into an ``EasyOKAPI``
    subfolder of it, the pointer is written, and the new root path is returned.
    The original data is left untouched. Raises ValueError on a bad or unwritable
    choice. The change takes effect on the next launch (root resolved at import).
    """
    if not parent_dir or not parent_dir.strip():
        raise ValueError("A folder is required.")
    return _relocate(os.path.join(_normalize(parent_dir), _ROOT_FOLDER_NAME))


def reset_to_default() -> str:
    """Copy the data back to the default location and remove the pointer."""
    return _relocate(state.default_data_root)
