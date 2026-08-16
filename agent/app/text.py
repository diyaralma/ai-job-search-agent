"""Metin normalizasyonu ve terim eşleştirme.

Hem kaynak katmanındaki kaba filtreler hem ön eleme skorlaması buradaki
eşleştirmeyi kullanıyor ki iki yerde farklı davranış oluşmasın.
"""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")

#: Unicode ayrıştırmasıyla (NFKD) ASCII'ye inmeyen harfler.
#: Türkçe noktasız "ı" bunların başında geliyor: ayrıştırılamadığı için
#: harf-dışı sayılıp boşluğa çevriliyordu ve "çalışmak" -> "cal smak" oluyordu.
#: Bu, Kırıkkale/Şişli/Bakırköy gibi her yer adını ve Türkçe her terimi bozar.
_CHAR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae",
    "ß": "ss", "đ": "d", "Đ": "d", "ł": "l", "Ł": "l", "þ": "th", "ð": "d",
})


def normalize(text: str) -> str:
    """Aksanları düşür, küçült, harf/rakam dışını boşluğa çevir."""
    text = text.translate(_CHAR_MAP).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", text).strip()


def term_in(haystack_norm: str, term: str) -> bool:
    """Kelime sınırına saygılı eşleşme.

    Düz `in` kullanmak "AWS" terimini "laws" içinde, "R" terimini neredeyse her
    metinde bulur ve eşleştirmeyi çöpe çevirir. normalize() harf/rakam dışını
    boşluğa çevirdiği için terimi boşlukla sarıp arıyoruz; çok kelimeli terimler
    ("machine learning") de aynı şekilde çalışıyor.

    `haystack_norm` normalize edilmiş olmalı; `term` ham verilebilir.
    """
    term_norm = normalize(term)
    if not term_norm:
        return False
    return f" {term_norm} " in f" {haystack_norm} "


def matches_any(text: str, terms: list[str]) -> bool:
    """Terim listesi boşsa her şey geçer; değilse en az biri eşleşmeli."""
    if not terms:
        return True
    haystack = normalize(text)
    return any(term_in(haystack, t) for t in terms if t)
