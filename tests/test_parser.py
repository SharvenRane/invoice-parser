import pytest

from src.parser import InvoiceParser
from src.synth import make_invoice
from src.tokens import BBox, Token, load_tokens


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("style", ["iso", "slash", "long"])
def test_parser_recovers_ground_truth(seed, style):
    inv = make_invoice(seed=seed, date_style=style)
    parsed = InvoiceParser().parse(inv.tokens)
    assert parsed.vendor == inv.vendor
    assert parsed.date_iso == inv.date_iso
    assert parsed.total == inv.total


def test_total_is_grand_total_not_subtotal():
    # The generated invoice always has subtotal < total because tax is added.
    # The parser must return the grand total bound to the "Total Due:" label,
    # not the subtotal nor the tax line that share the same money column.
    from src import patterns

    inv = make_invoice(seed=3)
    parsed = InvoiceParser().parse(inv.tokens)
    assert parsed.total == inv.total

    # Pull every amount that sits in the totals column and confirm the grand
    # total is the largest of subtotal, tax and total (proving it is not the
    # subtotal). We restrict to the right hand money column to avoid the invoice
    # number and year tokens that also parse as numbers elsewhere on the page.
    column_amounts = []
    for t in inv.tokens:
        m = patterns.parse_money(t.text)
        if m is not None and t.box.x0 >= 460 and t.text.startswith("$"):
            column_amounts.append(m)
    assert parsed.total == max(column_amounts)


def test_total_uses_position_not_just_largest_number():
    # Construct a case where the largest number on the page is NOT the total.
    # A line item costs 999.00 but the grand total is 50.00. Only position
    # (the amount sitting to the right of "Total Due:") gives the right answer.
    records = [
        # vendor
        ("Acme", 40, 40, 80, 54),
        # a pricey line item, far larger than the total
        ("Widget", 40, 200, 90, 214),
        ("$999.00", 470, 200, 540, 214),
        # the real total, smaller
        ("Total", 360, 300, 400, 314),
        ("Due:", 405, 300, 445, 314),
        ("$50.00", 470, 300, 540, 314),
    ]
    tokens = load_tokens(records)
    parsed = InvoiceParser().parse(tokens)
    assert parsed.total == 50.00
    # And the box it read from is the one on the total row, not the line item.
    assert parsed.total_box is not None
    assert parsed.total_box.y0 == 300


def test_total_binds_to_label_on_same_row_only():
    # Two amounts in the same column: subtotal above, total below. The parser
    # must pick the one on the Total row, proving it uses vertical position.
    records = [
        ("Subtotal:", 360, 100, 430, 114),
        ("$80.00", 470, 100, 540, 114),
        ("Total", 360, 130, 400, 144),
        ("Due:", 405, 130, 445, 144),
        ("$120.00", 470, 130, 540, 144),
    ]
    tokens = load_tokens(records)
    parsed = InvoiceParser().parse(tokens)
    assert parsed.total == 120.00
    assert parsed.total_box.y0 == 130


def test_date_binds_to_label_position():
    # Two dates on the page. One is a "ship date" we want to ignore, one is the
    # invoice date. Position relative to the "Invoice Date:" label disambiguates.
    records = [
        ("Ship", 40, 100, 70, 114),
        ("Date:", 75, 100, 115, 114),
        ("2020-01-01", 200, 100, 280, 114),
        ("Invoice", 40, 130, 90, 144),
        ("Date:", 95, 130, 135, 144),
        ("2023-07-14", 200, 130, 280, 144),
    ]
    tokens = load_tokens(records)
    parsed = InvoiceParser().parse(tokens)
    assert parsed.date_iso == "2023-07-14"
    assert parsed.date_box.y0 == 130


def test_vendor_is_top_block_not_amount_or_label():
    inv = make_invoice(seed=5)
    parsed = InvoiceParser().parse(inv.tokens)
    assert parsed.vendor == inv.vendor
    # The vendor should not be the word INVOICE nor an amount.
    assert "$" not in (parsed.vendor or "")
    assert (parsed.vendor or "").lower() != "invoice"


def test_empty_document_returns_none_fields():
    parsed = InvoiceParser().parse([])
    assert parsed.vendor is None
    assert parsed.date_iso is None
    assert parsed.total is None


def test_parser_is_deterministic_across_runs():
    a = InvoiceParser().parse(make_invoice(seed=2).tokens)
    b = InvoiceParser().parse(make_invoice(seed=2).tokens)
    assert (a.vendor, a.date_iso, a.total) == (b.vendor, b.date_iso, b.total)


def test_multi_token_long_date_to_the_right_of_label():
    # "Invoice Date:" then a three token long date form.
    records = [
        ("Invoice", 360, 90, 410, 104),
        ("Date:", 415, 90, 455, 104),
        ("July", 470, 90, 500, 104),
        ("14,", 505, 90, 525, 104),
        ("2023", 530, 90, 565, 104),
    ]
    tokens = load_tokens(records)
    parsed = InvoiceParser().parse(tokens)
    assert parsed.date_iso == "2023-07-14"
