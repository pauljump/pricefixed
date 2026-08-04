"""Conservative extraction of explicit apartment labels from public-record text."""
import re


_MARKER = re.compile(
    r"\b(?:APTS?\.?(?:'S)?|APARTMENTS?|DWELLING\s+UNITS?|RESIDENTIAL\s+UNITS?)"
    r"\s*(?:(?:NO|NOS)\.?\s*|#\s*)?",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[A-Z]?\d+(?:\s+[A-Z]\b|[A-Z0-9]*)?(?:(?:/|-)[A-Z0-9]+)*", re.IGNORECASE)
_SEPARATOR = re.compile(
    r"\s*(?:,|&|\+|;|\.|AND\b)\s*"
    r"(?:(?:APTS?\.?|APARTMENTS?)\s*)?(?:(?:NO|NOS)\.?\s*|#\s*)?",
    re.IGNORECASE,
)
_PART = re.compile(r"(?P<prefix>[A-Z]*)(?P<number>\d+)(?P<suffix>[A-Z]*)", re.IGNORECASE)
_INHERITED_SUFFIX = re.compile(r"[A-Z]\b", re.IGNORECASE)
_SPACED_SUFFIX_LIST = re.compile(r"(?P<suffixes>(?:\s+[A-Z]\b){2,})", re.IGNORECASE)
_CONCATENATED_PROSE = re.compile(
    r"^(?P<label>[A-Z]{0,2}\d+[A-Z]{0,3}?)(?:"
    r"INCLUDING|EXISTING|INSTALL(?:ATION)?|PROPOSED|MINOR|MNR|WITH|AND|ONLY"
    r")[A-Z]*$",
    re.IGNORECASE,
)
_TRAILING_NO = re.compile(r"^(?P<label>[A-Z]{0,2}\d+[A-Z]{0,3})NO$", re.IGNORECASE)
_PROSE_AFTER_NO = re.compile(
    r"\s*(?:CHANGE|WORK|INTERIOR|ALTERATION|RENOVATION|INSTALLATION|MODIFICATION|"
    r"OCCUPANCY|USE|EGRESS|PROPOSED|NEW)\b",
    re.IGNORECASE,
)
_THRU_RANGE = re.compile(
    r"^(?P<prefix>[A-Z]{0,2})(?P<start>\d+)(?P<suffix>[A-Z]{1,2})"
    r"THRU(?P<end>\d+)(?P<end_suffix>[A-Z]{1,2})$",
    re.IGNORECASE,
)


def _plausible_label(label, allow_ordinal=False):
    if label.isdigit() and len(label) > 4:
        return False
    floor = r"\d+(?:(?:ST|ND|RD|TH)(?:FL|FLO|FLOOR)?|FL|FLO|FLOOR)"
    return allow_ordinal or not re.fullmatch(floor, label)


def _expand_thru_range(token):
    match = _THRU_RANGE.fullmatch(token)
    if not match:
        return None
    if match.group("suffix") != match.group("end_suffix"):
        return []
    start = int(match.group("start"))
    end = int(match.group("end"))
    if end < start or end - start > 50:
        return []
    return [
        f"{match.group('prefix')}{number}{match.group('suffix')}"
        for number in range(start, end + 1)
    ]


def _expand_token(token, following="", allow_ordinal=False):
    token = re.sub(r"\s+", "", token.upper())
    if not re.fullmatch(r"[A-Z0-9/-]+", token):
        return []
    if "/" not in token and "-" not in token:
        trailing_no = _TRAILING_NO.fullmatch(token)
        if trailing_no and _PROSE_AFTER_NO.match(following):
            token = trailing_no.group("label")
        expanded_range = _expand_thru_range(token)
        if expanded_range is not None:
            return expanded_range
        prose = _CONCATENATED_PROSE.fullmatch(token)
        if prose:
            token = prose.group("label")
        return [token] if _plausible_label(token, allow_ordinal) else []
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
        raw_token = token.group(0)
        labels.extend(_expand_token(raw_token, tail[token.end():]))
        cursor = token.end() - (3 if raw_token.upper().endswith("AND") else 0)
        while True:
            separator = _SEPARATOR.match(tail, cursor)
            if not separator:
                suffixes = _SPACED_SUFFIX_LIST.match(tail, cursor)
                previous = _PART.fullmatch(labels[-1]) if labels else None
                if suffixes and previous and previous.group("suffix"):
                    labels.extend(
                        previous.group("prefix") + previous.group("number") + suffix
                        for suffix in re.findall(r"[A-Z]", suffixes.group("suffixes").upper())
                    )
                    cursor = suffixes.end()
                    continue
                break
            token = _TOKEN.match(tail, separator.end())
            if not token:
                suffix = _INHERITED_SUFFIX.match(tail, separator.end())
                previous = _PART.fullmatch(labels[-1]) if labels else None
                if suffix and previous and previous.group("suffix"):
                    labels.append(
                        previous.group("prefix") + previous.group("number")
                        + suffix.group(0).upper()
                    )
                    cursor = suffix.end()
                    continue
                break
            raw_token = token.group(0)
            previous = _PART.fullmatch(labels[-1]) if labels else None
            current = _PART.fullmatch(re.sub(r"\s+", "", raw_token))
            same_number_continuation = bool(
                previous and current
                and previous.group("prefix").upper() == current.group("prefix").upper()
                and previous.group("number") == current.group("number")
                and len(previous.group("suffix")) == 2
                and len(current.group("suffix")) == 2
                and previous.group("suffix")[0].upper() == current.group("suffix")[0].upper()
            )
            labels.extend(
                _expand_token(
                    raw_token, tail[token.end():],
                    allow_ordinal=same_number_continuation,
                )
            )
            cursor = token.end() - (3 if raw_token.upper().endswith("AND") else 0)
    return list(dict.fromkeys(label for label in labels if label))
