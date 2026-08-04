"""Conservative extraction of explicit apartment labels from public-record text."""
import re


_MARKER = re.compile(
    r"\b(?:APTS?\.?|APARTMENTS?|DWELLING\s+UNITS?|RESIDENTIAL\s+UNITS?)"
    r"\s*(?:(?:NO|NOS)\.?\s*|#\s*)?",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[A-Z]?\d+(?:\s+[A-Z]\b|[A-Z0-9]*)?(?:(?:/|-)[A-Z0-9]+)*", re.IGNORECASE)
_SEPARATOR = re.compile(
    r"\s*(?:,|&|;|\.|\bAND\b)\s*"
    r"(?:(?:APTS?\.?|APARTMENTS?)\s*)?(?:(?:NO|NOS)\.?\s*|#\s*)?",
    re.IGNORECASE,
)
_PART = re.compile(r"(?P<prefix>[A-Z]*)(?P<number>\d+)(?P<suffix>[A-Z]*)", re.IGNORECASE)


def _plausible_label(label):
    return not re.fullmatch(r"\d+(?:ST|ND|RD|TH)", label)


def _expand_token(token):
    token = re.sub(r"\s+", "", token.upper())
    if not re.fullmatch(r"[A-Z0-9/-]+", token):
        return []
    if "/" not in token and "-" not in token:
        return [token] if _plausible_label(token) else []
    parts = re.split(r"[/-]", token)
    first = _PART.fullmatch(parts[0])
    if not first or any(not part for part in parts):
        return []
    expanded = [parts[0]]
    for part in parts[1:]:
        if part.isalpha():
            if len(part) != 1:
                return expanded
            inherited = first.group("prefix") + first.group("number") + part
            # "7-D" is one punctuated label. "12B/C" names 12B and 12C.
            if not first.group("suffix"):
                expanded[0] = inherited
            else:
                expanded.append(inherited)
        elif _PART.fullmatch(part):
            expanded.append(part)
        else:
            return []
    # "Apartment 2/3D" is not enough to decide whether 2 is a label, floor,
    # or half of a combined designation. Keep the source row but make no claim.
    if (not first.group("prefix") and not first.group("suffix") and
            any((_PART.fullmatch(part).group("suffix") if _PART.fullmatch(part) else "")
                for part in parts[1:])):
        return []
    return [label for label in expanded if _plausible_label(label)]


def extract_explicit_unit_labels(text):
    """Return labels attached to an explicit apartment/dwelling-unit marker.

    A short comma/and/period-separated label list is accepted. Ordinary prose
    ends the list because the next token must begin with a digit or letter-digit.
    """
    text = str(text or "")
    labels = []
    for marker in _MARKER.finditer(text):
        tail = text[marker.end():marker.end() + 120]
        token = _TOKEN.match(tail)
        if not token:
            continue
        labels.extend(_expand_token(token.group(0)))
        cursor = token.end()
        while True:
            separator = _SEPARATOR.match(tail, cursor)
            if not separator:
                break
            token = _TOKEN.match(tail, separator.end())
            if not token:
                break
            labels.extend(_expand_token(token.group(0)))
            cursor = token.end()
    return list(dict.fromkeys(label for label in labels if label))
