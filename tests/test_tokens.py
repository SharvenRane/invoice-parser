import pytest

from src.tokens import BBox, Token, load_tokens


def test_bbox_geometry():
    b = BBox(0, 0, 10, 20)
    assert b.width == 10
    assert b.height == 20
    assert b.cx == 5
    assert b.cy == 10


def test_bbox_rejects_degenerate():
    with pytest.raises(ValueError):
        BBox(10, 0, 0, 5)


def test_vertical_overlap_same_row_is_high():
    a = BBox(0, 100, 50, 114)
    b = BBox(60, 101, 90, 115)  # nearly the same y band
    assert a.vertical_overlap(b) > 0.8


def test_vertical_overlap_different_rows_is_zero():
    a = BBox(0, 100, 50, 114)
    b = BBox(0, 200, 50, 214)
    assert a.vertical_overlap(b) == 0.0


def test_horizontal_gap_sign():
    left = BBox(0, 0, 50, 14)
    right = BBox(70, 0, 120, 14)
    # gap from left's right edge (50) to right's left edge (70) is 20
    assert left.horizontal_gap(right) == 20
    # reversed: the other token sits to the left, so the gap is negative
    assert right.horizontal_gap(left) < 0


def test_load_tokens_from_records():
    toks = load_tokens([("Hello", 0, 0, 30, 14), ("World", 35, 0, 70, 14)])
    assert len(toks) == 2
    assert toks[0].text == "Hello"
    assert toks[0].norm == "hello"
    assert toks[1].box.x0 == 35
