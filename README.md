# invoice-parser

Parse invoices into structured fields from token text and layout positions. The
parser reads a flat list of OCR style tokens, each carrying its text and a
bounding box, and recovers three fields: the vendor, the invoice date, and the
grand total.

The point of the project is that text alone is not enough. An invoice usually
has a subtotal, a tax line, and a grand total stacked in the same money column,
all with the same dollar surface form. A plain regex over the page text cannot
tell which number is the one you actually owe. This parser uses where the tokens
sit on the page to bind a value to its label, so the total it returns is the one
on the same row as "Total Due", not the largest number it happened to find.

## How the data is shaped

A document is a list of `Token` objects. Each token has its recognized text and
a `BBox` in page coordinates, with the origin at the top left, x growing to the
right and y growing downward. That is the same convention most OCR engines and
PDF text layers use, so once you flatten an OCR export into `(text, x0, y0, x1,
y1)` records you can feed it straight in:

```python
from src import InvoiceParser, load_tokens

records = [
    ("Globex", 40, 40, 90, 54),
    ("Invoice", 360, 90, 410, 104),
    ("Date:", 415, 90, 455, 104),
    ("2023-07-14", 470, 90, 545, 104),
    ("Total", 360, 300, 400, 314),
    ("Due:", 405, 300, 445, 314),
    ("$120.00", 470, 300, 540, 314),
]
parsed = InvoiceParser().parse(load_tokens(records))
print(parsed.vendor, parsed.date_iso, parsed.total)
```

## How position is used

The `BBox` type knows two things the parser leans on. The first is vertical
overlap: two tokens belong to the same text row when the shorter of their two
boxes is mostly covered by the other in the y direction. The second is the
horizontal gap from one box to the next, which tells the parser whether a token
sits to the right of a label or in a different column entirely.

With those two primitives the field logic reads naturally:

- **Total.** Find the run of tokens that spells a total label such as "Total
  Due", in priority order so a generic "Total" only wins when nothing more
  specific is present. Take the money token on that same row, just to the right.
  If the page has no usable total label, fall back to the largest amount.
- **Date.** Find the date label, then read the value to its right. Long forms
  such as "July 14, 2023" arrive split across several tokens, so the parser
  joins consecutive tokens until the join parses as a date.
- **Vendor.** Look in the top quarter of the page, group tokens into rows, and
  take the first row that is not a heading, a field label, an amount, a date, an
  email, or a street address. When a row spans two columns, for instance a
  vendor name on the left and an "INVOICE" heading on the right, the parser
  splits the row at the wide gap and keeps the leftmost column.

Dates come back normalized to ISO `YYYY-MM-DD` and money comes back as a float,
so downstream code never has to deal with the surface form again.

## Synthetic invoices

There is no real OCR engine here. `src/synth.py` lays out a small invoice on a
virtual US Letter page and emits tokens with believable positions: a vendor
block at the top, a metadata block with the invoice number and date, a line item
table, and a totals block at the bottom right. It is deterministic given a seed
and it returns the ground truth fields alongside the tokens, which is what the
tests check against. The geometry it produces is the same shape an OCR front end
would hand over, so the parser under test runs exactly as it would on real input.

The date can be rendered in three styles (`iso`, `slash`, `long`) so the tests
confirm the date logic handles several common surface forms.

## Layout

```
src/
  tokens.py    Token and BBox primitives, plus overlap and gap geometry
  patterns.py  money and date regexes and their normalizers
  synth.py     deterministic synthetic invoice generator
  parser.py    the layout aware parser
tests/
  test_tokens.py    geometry of boxes, overlap and gap signs
  test_patterns.py  money and date parsing across surface forms
  test_parser.py    field recovery and the position behavior checks
```

## Tests

The tests are behavior checks, not snapshots. The headline cases build documents
where text alone would give the wrong answer and confirm the parser still gets it
right:

- a page whose largest number is a line item, where only the position of "Total
  Due" recovers the real, smaller total
- a subtotal and a total in the same money column, where the parser must use the
  row to pick the total
- two dates on the page, where the value next to the invoice date label is the
  one returned

It also sweeps the synthetic generator across eight seeds and all three date
styles and asserts the recovered vendor, date, and total match ground truth.

Run them with:

```
cd invoice-parser
python -m pytest tests/ -q
```

A clean run reports 45 passing tests.

## Requirements

The core code uses only the Python standard library. The only dependency is
pytest to run the test suite.
