"""Text normalization and term matching.

Both the coarse filters in the source layer and the pre-filter scoring use the
matching here, so the two cannot drift apart.
"""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")

#: Letters that NFKD decomposition does not reduce to ASCII.
#: The Turkish dotless "ı" is the worst offender: it does not decompose, so it
#: was treated as a non-letter and replaced by a space, turning "çalışmak" into
#: "cal smak". That breaks every place name like Kırıkkale/Şişli/Bakırköy and
#: every Turkish term.
_CHAR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae",
    "ß": "ss", "đ": "d", "Đ": "d", "ł": "l", "Ł": "l", "þ": "th", "ð": "d",
})


def normalize(text: str) -> str:
    """Strip accents, lowercase, turn everything non-alphanumeric into spaces."""
    text = text.translate(_CHAR_MAP).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", text).strip()


def term_in(haystack_norm: str, term: str) -> bool:
    """Word-boundary aware matching.

    A plain `in` finds "AWS" inside "laws" and "R" in almost any text, which
    makes matching worthless. Since normalize() turns everything
    non-alphanumeric into spaces, we wrap the term in spaces and search for
    that; multi-word terms ("machine learning") work the same way.

    `haystack_norm` must already be normalized; `term` may be raw.
    """
    term_norm = normalize(term)
    if not term_norm:
        return False
    return f" {term_norm} " in f" {haystack_norm} "


def matches_any(text: str, terms: list[str]) -> bool:
    """An empty term list matches everything; otherwise at least one must hit."""
    if not terms:
        return True
    haystack = normalize(text)
    return any(term_in(haystack, t) for t in terms if t)
