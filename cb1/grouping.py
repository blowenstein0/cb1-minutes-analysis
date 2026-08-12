"""Parse minutes filenames: date, part number, revised flag, doc-type hint.

Filename dates are HINTS, not truth — the identify stage derives the
canonical date from page-1 content and does the grouping; filename parsing
supplies the hints and lets us cross-check content dates.

Real-world formats this handles (all present in tests/fixtures/index_hrefs.txt):
  jan2016.pdf                          month-abbrev + year, no day
  minutes-20221109.pdf                 YYYYMMDD
  minutes-202111.pdf                   YYYYMM, no day
  ...-10-13-16.pdf / ..._2_15_17.pdf   M-D-YY with -, _ or space
  ...-9-8-2020.pdf                     M-D-YYYY
  ..._292021_...pdf                    MDYYYY concatenated (2/9/2021)
  ...-December-19-2023-full.pdf        month-name D YYYY
  ...-Part-1.pdf / ...-12-10-24-2.pdf  explicit and bare trailing part numbers
  Pages-from-Minutes-3.pdf             part number, NO date (content resolves)
  REVISED-... / ..._revised / ...-rev  revised re-uploads
"""

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

SEP = r"[-_ ]"
YMD_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})(?!\d)")
YM_RE = re.compile(r"(20\d{2})(\d{2})(?!\d)")
MONTHNAME_RE = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"
    rf"(?:{SEP}(\d{{1,2}}))?{SEP}?(20\d{{2}}|\d{{2}})(?!\d)"
)
NUMERIC_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}}){SEP}(\d{{1,2}}){SEP}(20\d{{2}}|\d{{2}})(?!\d)"
)
CONCAT_RE = re.compile(r"(?<!\d)(\d{2,4})(20\d{2})(?!\d)")
PART_RE = re.compile(rf"part{SEP}?(\d{{1,2}})", re.IGNORECASE)
TRAILING_NUM_RE = re.compile(r"[-_](\d)$")


def _year(y: int) -> int:
    return y if y >= 2000 else 2000 + y


def _valid(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


@dataclass(frozen=True)
class FileRef:
    href: str
    filename: str
    date_guess: date | None  # full date parsed from filename
    year_month_guess: tuple[int, int] | None  # when only Y+M parseable
    part_no: int | None
    is_revised: bool
    doc_type_hint: str  # combined|public_hearing|special|committee|unknown


def parse_date(stem: str) -> tuple[date | None, tuple[int, int] | None, tuple[int, int]]:
    """Extract (full_date, year_month, matched_span) from a filename stem.

    Span is needed so part-number detection can ignore digits that belong
    to the date itself.
    """
    s = stem.lower()

    m = YMD_RE.search(s)
    if m:
        d = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            return d, None, m.span()

    m = MONTHNAME_RE.search(s)
    if m:
        month = MONTHS[m.group(1)]
        year = _year(int(m.group(3)))
        if m.group(2):
            d = _valid(year, month, int(m.group(2)))
            if d:
                return d, None, m.span()
        return None, (year, month), m.span()

    m = NUMERIC_RE.search(s)
    if m:
        d = _valid(_year(int(m.group(3))), int(m.group(1)), int(m.group(2)))
        if d:
            return d, None, m.span()

    m = YM_RE.search(s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return None, (year, month), m.span()

    m = CONCAT_RE.search(s)
    if m:
        digits, year = m.group(1), _year(int(m.group(2)))
        candidates = []
        for i in (1, 2):
            if i < len(digits) and len(digits) - i <= 2:
                cand = _valid(year, int(digits[:i]), int(digits[i:]))
                if cand:
                    candidates.append(cand)
        if len(candidates) == 1:  # ambiguous splits stay unresolved
            return candidates[0], None, m.span()

    return None, None, (0, 0)


def parse_part(stem: str, date_span: tuple[int, int]) -> int | None:
    m = PART_RE.search(stem)
    if m:
        return int(m.group(1))
    m = TRAILING_NUM_RE.search(stem)
    if m and m.start(1) >= date_span[1]:  # digit not inside the date match
        return int(m.group(1))
    return None


def parse_doc_type(stem: str) -> str:
    s = stem.lower()
    if "special" in s:
        return "special"
    if "committee" in s:
        return "committee"
    if "combine" in s:  # matches combined + the "Combine_" typo
        return "combined"
    if "public-hearing" in s.replace("_", "-") and "board" not in s:
        return "public_hearing"
    return "unknown"


def parse_href(href: str) -> FileRef:
    filename = href.rsplit("/", 1)[-1]
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    d, ym, span = parse_date(stem)
    return FileRef(
        href=href,
        filename=filename,
        date_guess=d,
        year_month_guess=ym,
        part_no=parse_part(stem, span),
        is_revised="revised" in stem.lower() or bool(re.search(r"[-_]rev$", stem.lower())),
        doc_type_hint=parse_doc_type(stem),
    )
