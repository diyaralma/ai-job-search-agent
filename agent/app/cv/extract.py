"""Yüklenen CV dosyasından düz metin çıkarır.

Not — bilinçli bir ödün: Claude Code CLI'ya PDF'i `document` bloğu olarak
gönderemiyoruz (o yol yalnızca Messages API'sinde var), bu yüzden metni yerel
olarak çıkarıyoruz. Tek kolonlu standart CV'lerde sorun yok; ağır tasarımlı,
iki kolonlu veya tablo yerleşimli PDF'lerde okuma sırası bozulabiliyor.
Çıkarım anlamlı metin vermezse kullanıcıyı DOCX/TXT'ye yönlendiriyoruz —
sessizce bozuk metinle devam etmektense açık hata vermek daha iyi.
"""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader

MAX_TEXT_CHARS = 200_000
#: Bunun altındaki çıktı "PDF taranmış görüntü / metin katmanı yok" demek
MIN_USEFUL_CHARS = 120

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedCV(ValueError):
    pass


def _suffix(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _docx_to_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(line for line in lines if line.strip())


def _pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - tek bozuk sayfa tüm CV'yi düşürmesin
            continue
    return "\n".join(pages)


def to_text(filename: str, data: bytes) -> str:
    """CV dosyasını modele verilecek düz metne çevirir."""
    suffix = _suffix(filename)
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedCV(
            f"Desteklenmeyen dosya türü: {suffix or 'uzantısız'}. "
            f"Desteklenenler: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if not data:
        raise UnsupportedCV("Dosya boş.")

    if suffix == ".pdf":
        text = _pdf_to_text(data)
        if len(text.strip()) < MIN_USEFUL_CHARS:
            raise UnsupportedCV(
                "PDF'den metin çıkarılamadı — dosya taranmış görüntü olabilir. "
                "CV'yi DOCX veya TXT olarak yükleyin."
            )
    elif suffix == ".docx":
        text = _docx_to_text(data)
    else:
        text = data.decode("utf-8", errors="replace")

    if len(text.strip()) < MIN_USEFUL_CHARS:
        raise UnsupportedCV("Dosyadan okunabilir metin çıkarılamadı.")
    return text[:MAX_TEXT_CHARS]
