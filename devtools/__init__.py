"""EasyOKAPI developer tools — NOT part of what users receive.

This package is the whole of the ``--monitor`` performance monitor: its
blueprint, its page, its counters and the attach-time wrappers it puts around
the production modules it observes. ``main.py`` knows one name from it
(``attach_monitor``) and imports it only behind the flag, so with the flag
absent nothing in here is loaded, let alone run.

It is excluded from the shipped build (``excludes`` in ``easyokapi.spec``, and
``export-ignore`` in ``.gitattributes`` for the source tarball) and stays in git
on ``main`` — it is a developer tool, not a secret. See ``devtools/README.md``
before adding a file here; the exclusions are per-package, not per-file, but
the reasoning for keeping them intact lives there.
"""

from .monitor import (
    MONITOR_PREFIX,
    attach_monitor,
    detach_monitor,
    is_enabled,
    is_frozen,
    monitor_url,
)

__all__ = [
    'MONITOR_PREFIX',
    'attach_monitor',
    'detach_monitor',
    'is_enabled',
    'is_frozen',
    'monitor_url',
]
