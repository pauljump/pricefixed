"""Normalization helpers for stable public-record identifiers."""

import re


def normalize_bbl(raw):
    """Return a canonical 10-digit NYC BBL, or ``None`` when it is unsafe.

    Some legacy DOB exports padded the four-digit lot with one extra leading zero,
    producing values such as ``10097800001`` for ``1009780001``. That exact fixed-
    width shape is repaired; other non-10-digit values stay rejected.
    """
    text = str(raw or "").strip()
    match = re.fullmatch(r"(\d+)(?:\.0+)?", text)
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 10 and digits[0] in "12345":
        return digits
    if len(digits) == 11 and digits[0] in "12345" and digits[6] == "0":
        repaired = digits[:6] + digits[7:]
        if len(repaired) == 10:
            return repaired
    return None
