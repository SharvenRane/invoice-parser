"""Token and bounding box primitives.

A document is represented as an ordered list of tokens. Each token carries the
recognized text plus a bounding box in page coordinates. The origin (0, 0) is the
top left corner, x grows to the right and y grows downward, matching the
convention used by most OCR engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class BBox:
    """An axis aligned bounding box in page coordinates.

    Coordinates are floats so that normalized boxes (0..1) and pixel boxes both
    fit. The box is half open is not assumed; we treat x0 <= x1 and y0 <= y1.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(
                f"degenerate box: ({self.x0}, {self.y0}, {self.x1}, {self.y1})"
            )

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def vertical_overlap(self, other: "BBox") -> float:
        """Fraction of the shorter box that overlaps the other vertically.

        Returns a value in [0, 1]. Two tokens on the same text line share most of
        their vertical extent, so a high value means "same row".
        """
        top = max(self.y0, other.y0)
        bottom = min(self.y1, other.y1)
        inter = max(0.0, bottom - top)
        shorter = min(self.height, other.height)
        if shorter <= 0:
            return 0.0
        return inter / shorter

    def horizontal_gap(self, other: "BBox") -> float:
        """Signed horizontal gap from the right edge of self to the left edge of other.

        Positive when ``other`` sits to the right of ``self`` with clear space
        between them. Negative when they overlap horizontally.
        """
        return other.x0 - self.x1


@dataclass(frozen=True)
class Token:
    """A single recognized text token placed on the page."""

    text: str
    box: BBox

    @property
    def norm(self) -> str:
        """Lowercased text with surrounding whitespace removed."""
        return self.text.strip().lower()


def load_tokens(records: Iterable[Sequence]) -> List[Token]:
    """Build a token list from raw records.

    Each record is ``(text, x0, y0, x1, y1)``. This is the shape an OCR export or
    a PDF text layer typically produces once flattened.
    """
    tokens: List[Token] = []
    for rec in records:
        text, x0, y0, x1, y1 = rec
        tokens.append(Token(str(text), BBox(float(x0), float(y0), float(x1), float(y1))))
    return tokens
