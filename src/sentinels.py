"""Non-numeric tokens a colorimeter value column can carry.

The device streams one of these in place of a number when a channel has no
reading to report (firmware ``src/serial_manager.py::_fmt``):

* ``OVFL`` — the sensor saturated.
* ``NONE`` — nothing to measure yet: a blank-needing measurement on a device
  that has not been blanked (a channel change resets the blanks).
* ``INF``  — a fully attenuated channel: zero counts through the cuvette, so the
  absorbance is genuinely infinite. Firmware branches that predate the token
  (``main``, ``open-plus``, ``open-uv``) write Python's own repr, ``inf``, so
  both spellings are accepted here and either one keeps the row valid.

Two rules follow from this, and both matter:

1. A row is validated as a whole. A value the pattern does not recognize drops
   the entire row — including the healthy channels in it — so the token list in
   ``TOKEN_PATTERN`` is what decides whether a session records anything at all.
2. ``float("INF")`` does *not* raise; it returns an infinity, which then poisons
   fits, JSON (``Infinity`` is not valid JSON) and Excel cells. Sentinels must
   therefore be filtered *before* any coercion — that is what ``to_number`` is
   for; ``try: float(v) except ValueError`` is not enough on its own.
"""

import math

NO_VALUE = "NONE"
OVERFLOW = "OVFL"
INFINITE = "INF"

# Exact strings the device can send (upper case), plus the legacy lower-case
# infinities from firmware that has not adopted the token yet.
SENTINELS = (NO_VALUE, OVERFLOW, INFINITE, "-INF", "inf", "-inf")

# Fragment for the CSV row validators: one non-numeric value cell.
TOKEN_PATTERN = r"(?:OVFL|NONE|[+-]?[Ii][Nn][Ff])"


def is_sentinel(value):
    """True when ``value`` is one of the device's non-numeric tokens."""
    return isinstance(value, str) and value.strip() in SENTINELS


def to_number(value, default=None):
    """``value`` as a finite float, or ``default`` when it is not one.

    Covers the three ways a value column fails to be a number: a sentinel token,
    unparseable text, and a parseable-but-infinite one (``INF``/``inf``/``nan``).
    """
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, str) and (is_sentinel(value) or not value.strip()):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default
