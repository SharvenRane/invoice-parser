"""Synthetic invoice generator.

We lay out a small invoice on a virtual page and emit tokens with realistic
positions. The layout has a vendor block at the top, a metadata block with the
invoice number and date, a line item table, and a totals block at the bottom
right. The generator is deterministic given a seed so tests can rely on it.

This is a stand in for a real OCR front end. The geometry it produces is the same
shape an OCR engine would hand to the parser, so the parser code under test is
exercised exactly as it would be in production.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .tokens import BBox, Token

PAGE_W = 612.0   # US Letter width in points
PAGE_H = 792.0
CHAR_W = 6.0     # rough monospace advance for placing word boxes
LINE_H = 14.0


_VENDORS = [
    "Globex Corporation",
    "Initech LLC",
    "Stark Industries",
    "Wayne Enterprises",
    "Acme Supplies Co",
    "Umbrella Logistics",
]


@dataclass
class Invoice:
    """A generated invoice plus the ground truth fields used by tests."""

    tokens: List[Token]
    vendor: str
    date_iso: str
    total: float
    invoice_number: str


def _words(text: str, x: float, y: float) -> List[Token]:
    """Place each whitespace separated word as its own token on one line."""
    out: List[Token] = []
    cursor = x
    for word in text.split(" "):
        if word == "":
            cursor += CHAR_W
            continue
        w = max(CHAR_W, len(word) * CHAR_W)
        out.append(Token(word, BBox(cursor, y, cursor + w, y + LINE_H)))
        cursor += w + CHAR_W  # trailing space
    return out


def _format_date(d, style: str) -> str:
    if style == "iso":
        return d.strftime("%Y-%m-%d")
    if style == "slash":
        return f"{d.month}/{d.day}/{d.year}"
    if style == "long":
        return d.strftime("%B %d, %Y").replace(" 0", " ")
    raise ValueError(style)


def make_invoice(seed: int = 0, date_style: str = "iso") -> Invoice:
    """Build one deterministic synthetic invoice.

    ``date_style`` is one of ``iso``, ``slash`` or ``long`` so tests can confirm
    the date parser handles several surface forms.
    """
    import datetime as dt

    rng = random.Random(seed)
    vendor = rng.choice(_VENDORS)
    inv_no = f"INV-{rng.randint(1000, 9999)}"

    # A date somewhere in a few year window.
    base = dt.date(2022, 1, 1)
    the_date = base + dt.timedelta(days=rng.randint(0, 1200))
    date_surface = _format_date(the_date, date_style)

    tokens: List[Token] = []

    # Vendor block, top left, larger and first on the page.
    tokens += _words(vendor, x=40.0, y=40.0)
    tokens += _words("123 Market Street", x=40.0, y=40.0 + LINE_H + 4)
    tokens += _words("billing@example.com", x=40.0, y=40.0 + 2 * (LINE_H + 4))

    # The word "INVOICE" as a heading, top right.
    tokens += _words("INVOICE", x=470.0, y=40.0)

    # Metadata block, upper right: label on the left, value to its right.
    meta_y = 90.0
    tokens += _words("Invoice Number:", x=360.0, y=meta_y)
    tokens += _words(inv_no, x=470.0, y=meta_y)
    tokens += _words("Invoice Date:", x=360.0, y=meta_y + LINE_H + 4)
    tokens += _words(date_surface, x=470.0, y=meta_y + LINE_H + 4)

    # Line item table. Build a subtotal from the items.
    table_top = 200.0
    tokens += _words("Description", x=40.0, y=table_top)
    tokens += _words("Qty", x=360.0, y=table_top)
    tokens += _words("Amount", x=470.0, y=table_top)

    n_items = rng.randint(2, 4)
    subtotal = 0.0
    row_y = table_top + LINE_H + 6
    for i in range(n_items):
        price = round(rng.uniform(10, 400), 2)
        subtotal += price
        tokens += _words(f"Service item {i + 1}", x=40.0, y=row_y)
        tokens += _words("1", x=360.0, y=row_y)
        tokens += _words(f"${price:,.2f}", x=470.0, y=row_y)
        row_y += LINE_H + 6

    subtotal = round(subtotal, 2)
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)

    # Totals block, bottom right. Labels sit to the LEFT of the values so the
    # parser must use horizontal position to bind label to amount.
    totals_top = row_y + 20
    label_x = 360.0
    value_x = 470.0
    tokens += _words("Subtotal:", x=label_x, y=totals_top)
    tokens += _words(f"${subtotal:,.2f}", x=value_x, y=totals_top)
    tokens += _words("Tax (8%):", x=label_x, y=totals_top + LINE_H + 4)
    tokens += _words(f"${tax:,.2f}", x=value_x, y=totals_top + LINE_H + 4)
    tokens += _words("Total Due:", x=label_x, y=totals_top + 2 * (LINE_H + 4))
    tokens += _words(f"${total:,.2f}", x=value_x, y=totals_top + 2 * (LINE_H + 4))

    return Invoice(
        tokens=tokens,
        vendor=vendor,
        date_iso=the_date.isoformat(),
        total=total,
        invoice_number=inv_no,
    )


def render_text(tokens: List[Token]) -> str:
    """Render tokens back into rough plain text, row by row.

    Useful for debugging and for a text only baseline. Tokens are grouped into
    rows by their vertical center then ordered left to right.
    """
    rows: List[Tuple[float, List[Token]]] = []
    for tok in sorted(tokens, key=lambda t: (t.box.cy, t.box.x0)):
        placed = False
        for ref_y, bucket in rows:
            if abs(tok.box.cy - ref_y) <= LINE_H * 0.6:
                bucket.append(tok)
                placed = True
                break
        if not placed:
            rows.append((tok.box.cy, [tok]))
    lines = []
    for _, bucket in rows:
        bucket.sort(key=lambda t: t.box.x0)
        lines.append(" ".join(t.text for t in bucket))
    return "\n".join(lines)
