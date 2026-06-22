"""Layout aware invoice parser.

The parser takes a flat list of tokens and recovers three fields: vendor, date
and total. It combines two signals:

  1. Text patterns. A token like ``$1,234.56`` looks like money; ``Total Due:``
     looks like a total label.
  2. Layout. The grand total amount is the money token that sits on the same row
     as the total label and just to its right. The date value sits next to the
     date label. The vendor is the first substantial line of text near the top of
     the page. Without position, a flat regex would confuse the subtotal, the tax
     line and the grand total because they share surface form.

The position logic is what makes this more than a regex. It is the part the tests
target directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import patterns
from .tokens import BBox, Token


@dataclass
class ParsedInvoice:
    vendor: Optional[str]
    date_iso: Optional[str]
    total: Optional[float]
    # Provenance: the box the total amount was read from, for debugging and tests.
    total_box: Optional[BBox] = None
    date_box: Optional[BBox] = None


class InvoiceParser:
    def __init__(
        self,
        row_overlap: float = 0.4,
        max_label_gap: float = 200.0,
        vendor_top_frac: float = 0.25,
    ) -> None:
        # Two tokens are on the same row when their vertical overlap is at least
        # this fraction of the shorter box.
        self.row_overlap = row_overlap
        # A value bound to a label must start within this many points to the
        # right of the label, otherwise it belongs to a different column.
        self.max_label_gap = max_label_gap
        # The vendor is searched within this fraction of the page height.
        self.vendor_top_frac = vendor_top_frac

    # --- public API -------------------------------------------------------

    def parse(self, tokens: List[Token]) -> ParsedInvoice:
        vendor = self._find_vendor(tokens)
        date_iso, date_box = self._find_date(tokens)
        total, total_box = self._find_total(tokens)
        return ParsedInvoice(
            vendor=vendor,
            date_iso=date_iso,
            total=total,
            total_box=total_box,
            date_box=date_box,
        )

    # --- row helpers ------------------------------------------------------

    def _same_row(self, a: Token, b: Token) -> bool:
        return a.box.vertical_overlap(b.box) >= self.row_overlap

    def _value_right_of(
        self, label_tokens: List[Token], all_tokens: List[Token]
    ) -> List[Token]:
        """Return tokens that lie on the label's row and to its right.

        ``label_tokens`` is the contiguous run that makes up the label phrase.
        We anchor on the rightmost label box so the returned values start past the
        whole phrase, then sort left to right.
        """
        anchor = max(label_tokens, key=lambda t: t.box.x1)
        out: List[Tuple[float, Token]] = []
        label_ids = {id(t) for t in label_tokens}
        for tok in all_tokens:
            if id(tok) in label_ids:
                continue
            if not self._same_row(anchor, tok):
                continue
            gap = anchor.box.horizontal_gap(tok.box)
            if gap < -2.0:  # token starts left of the label; wrong side
                continue
            if gap > self.max_label_gap:
                continue
            out.append((tok.box.x0, tok))
        out.sort(key=lambda pair: pair[0])
        return [t for _, t in out]

    def _find_label_run(
        self, tokens: List[Token], phrase: str
    ) -> Optional[List[Token]]:
        """Find a contiguous, same row run of tokens whose joined text matches.

        ``phrase`` is lowercased words. We slide a window over tokens ordered as
        given (reading order) and require the run to sit on one row.
        """
        words = phrase.split(" ")
        n = len(words)
        for i in range(len(tokens) - n + 1):
            window = tokens[i : i + n]
            joined = " ".join(t.norm.rstrip(":") for t in window)
            if joined != phrase:
                continue
            # All on the same row?
            ok = all(self._same_row(window[0], w) for w in window[1:])
            if ok:
                return window
        return None

    # --- field extractors -------------------------------------------------

    def _find_total(self, tokens: List[Token]) -> Tuple[Optional[float], Optional[BBox]]:
        """Find the grand total amount using label priority and position.

        We try total labels in priority order. For each, we look for the money
        token immediately to the right on the same row. We skip labels that are
        actually subtotal or tax lines. If no labelled total is found we fall back
        to the largest money token on the page, which on a well formed invoice is
        the grand total.
        """
        for label in patterns.TOTAL_LABELS:
            run = self._find_label_run(tokens, label)
            if run is None:
                continue
            # Guard: make sure this run is not part of a non total label like
            # "subtotal" (which contains "total"). The exact match in
            # _find_label_run already prevents that, but a single token
            # "Subtotal:" would never equal "total", so we are safe.
            values = self._value_right_of(run, tokens)
            for v in values:
                amt = patterns.parse_money(v.text)
                if amt is not None:
                    return amt, v.box
        # Fallback: largest money token anywhere.
        best: Optional[Tuple[float, BBox]] = None
        for tok in tokens:
            amt = patterns.parse_money(tok.text)
            if amt is None:
                continue
            if best is None or amt > best[0]:
                best = (amt, tok.box)
        if best is not None:
            return best
        return None, None

    def _find_date(self, tokens: List[Token]) -> Tuple[Optional[str], Optional[BBox]]:
        """Find the invoice date using a date label and its neighbor to the right.

        Falls back to the first date shaped token on the page if no label is
        present.
        """
        for label in patterns.DATE_LABELS:
            run = self._find_label_run(tokens, label)
            if run is None:
                continue
            values = self._value_right_of(run, tokens)
            # The date may be split across tokens (e.g. "July 14, 2023"), so we
            # try increasingly long joins of the value tokens.
            for end in range(1, len(values) + 1):
                joined = " ".join(t.text for t in values[:end])
                iso = patterns.parse_date(joined)
                if iso is not None:
                    return iso, values[0].box
        # Fallback: scan reading order for the first parseable date, joining up to
        # three consecutive tokens to catch long forms.
        for i in range(len(tokens)):
            for span in range(1, 4):
                window = tokens[i : i + span]
                joined = " ".join(t.text for t in window)
                iso = patterns.parse_date(joined)
                if iso is not None:
                    return iso, window[0].box
        return None, None

    def _find_vendor(self, tokens: List[Token]) -> Optional[str]:
        """Recover the vendor name from the top region of the page.

        The vendor block is the first text line near the top that is not a
        heading, a field label, an amount or a date. We group the top tokens into
        rows, drop rows that look like metadata, and take the first remaining row.
        """
        if not tokens:
            return None
        page_top = min(t.box.y0 for t in tokens)
        page_bottom = max(t.box.y1 for t in tokens)
        cutoff = page_top + (page_bottom - page_top) * self.vendor_top_frac

        top = [t for t in tokens if t.box.cy <= cutoff]
        if not top:
            return None

        rows = self._group_rows(top)
        for row in rows:
            # A row can span multiple columns (e.g. the vendor name on the left
            # and an "INVOICE" heading on the right). Split the row into column
            # segments wherever a large horizontal gap appears, then evaluate the
            # leftmost segment as the vendor candidate.
            segment = self._leading_segment(row)
            text = " ".join(t.text for t in segment).strip()
            low = text.lower()
            if not text:
                continue
            if low == "invoice":
                continue
            if any(lbl in low for lbl in ("invoice number", "invoice date", "date")):
                continue
            if patterns.looks_like_money(text) or patterns.looks_like_date(text):
                continue
            if "@" in text or text[0].isdigit():
                # email or street address line
                continue
            return text
        return None

    def _leading_segment(self, row: List[Token]) -> List[Token]:
        """Return the leftmost column segment of a row.

        Tokens are split into segments wherever the gap to the next token exceeds
        a column threshold. This separates a left aligned vendor name from a right
        aligned heading that happens to share the same vertical band.
        """
        if not row:
            return row
        ordered = sorted(row, key=lambda t: t.box.x0)
        column_gap = 40.0  # points; wider than a normal inter word space
        segment = [ordered[0]]
        for prev, cur in zip(ordered, ordered[1:]):
            if prev.box.horizontal_gap(cur.box) > column_gap:
                break
            segment.append(cur)
        return segment

    def _group_rows(self, tokens: List[Token]) -> List[List[Token]]:
        """Group tokens into rows by vertical overlap, ordered top to bottom."""
        ordered = sorted(tokens, key=lambda t: (t.box.cy, t.box.x0))
        rows: List[List[Token]] = []
        for tok in ordered:
            placed = False
            for row in rows:
                if self._same_row(row[0], tok):
                    row.append(tok)
                    placed = True
                    break
            if not placed:
                rows.append([tok])
        for row in rows:
            row.sort(key=lambda t: t.box.x0)
        rows.sort(key=lambda r: min(t.box.y0 for t in r))
        return rows
