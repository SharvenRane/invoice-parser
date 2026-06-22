from src import patterns


def test_parse_money_handles_thousands_and_symbol():
    assert patterns.parse_money("$1,234.56") == 1234.56
    assert patterns.parse_money("1234.56") == 1234.56
    assert patterns.parse_money("USD 99.00") == 99.00
    assert patterns.parse_money("€10") == 10.0


def test_parse_money_returns_none_for_non_money():
    assert patterns.parse_money("Total Due") is None
    assert patterns.parse_money("") is None


def test_parse_date_iso():
    assert patterns.parse_date("2023-07-14") == "2023-07-14"


def test_parse_date_slash_is_month_first():
    assert patterns.parse_date("7/14/2023") == "2023-07-14"


def test_parse_date_long_forms():
    assert patterns.parse_date("July 14, 2023") == "2023-07-14"
    assert patterns.parse_date("14 Jul 2023") == "2023-07-14"


def test_parse_date_rejects_garbage():
    assert patterns.parse_date("not a date") is None
    assert patterns.parse_date("13/40/2023") is None  # invalid month/day


def test_label_lists_are_consistent():
    # "total" must be last so more specific labels win first.
    assert patterns.TOTAL_LABELS[-1] == "total"
    assert "subtotal" in patterns.NON_TOTAL_LABELS
