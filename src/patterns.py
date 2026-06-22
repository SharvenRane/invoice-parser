"""Regular expressions and normalizers for invoice fields.

These are deliberately small and readable. They convert the messy surface forms
that appear on real invoices into canonical Python values: a float for money and
an ISO date string for dates.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

# Money: optional currency symbol, thousands separators, two decimal places.
# Examples matched: $1,234.56  1234.56  €99.00  USD 12.00
MONEY_RE = re.compile(
    r"""
    (?P<cur>[$€£]|usd|eur|gbp)?     # optional currency marker
    \s*
    (?P<amt>
        \d{1,3}(?:,\d{3})*(?:\.\d{2})   # grouped thousands with cents
        | \d+\.\d{2}                     # plain dotted cents
        | \d+                            # bare integer
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Labels that introduce the grand total. Order matters for priority elsewhere.
TOTAL_LABELS = (
    "total due",
    "amount due",
    "balance due",
    "grand total",
    "total",
)

# Labels we explicitly do NOT want to read as the grand total.
NON_TOTAL_LABELS = (
    "subtotal",
    "sub total",
    "tax",
    "vat",
    "discount",
    "shipping",
)

DATE_LABELS = (
    "invoice date",
    "date of issue",
    "issue date",
    "date",
)

# A few common date surface forms.
_DATE_PATTERNS = (
    # 2023-07-14
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    # 07/14/2023 or 7/14/2023
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    # 14 Jul 2023  /  July 14, 2023
    (
        re.compile(
            r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b"
        ),
        "dmonthy",
    ),
    (
        re.compile(
            r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b"
        ),
        "monthdy",
    ),
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_money(text: str) -> Optional[float]:
    """Extract the first money amount from ``text`` as a float, or None."""
    m = MONEY_RE.search(text)
    if not m:
        return None
    amt = m.group("amt").replace(",", "")
    try:
        return float(amt)
    except ValueError:
        return None


def _month_to_int(name: str) -> Optional[int]:
    return _MONTHS.get(name.strip().lower()[:3])


def parse_date(text: str) -> Optional[str]:
    """Extract the first recognizable date and return it as ISO ``YYYY-MM-DD``."""
    for rx, kind in _DATE_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "mdy":
                mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "dmonthy":
                d = int(m.group(1))
                mo = _month_to_int(m.group(2))
                y = int(m.group(3))
            elif kind == "monthdy":
                mo = _month_to_int(m.group(1))
                d = int(m.group(2))
                y = int(m.group(3))
            else:  # pragma: no cover - defensive
                continue
            if mo is None:
                continue
            return _dt.date(y, mo, d).isoformat()
        except (ValueError, TypeError):
            continue
    return None


def looks_like_money(text: str) -> bool:
    return parse_money(text) is not None


def looks_like_date(text: str) -> bool:
    return parse_date(text) is not None
