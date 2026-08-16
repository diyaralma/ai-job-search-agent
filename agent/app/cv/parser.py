"""CV -> CandidateProfile çıkarımı."""

from __future__ import annotations

from ..llm import structured
from ..schemas import CandidateProfile
from .extract import to_text

SYSTEM = """Sen teknik işe alım uzmanısın. Sana bir adayın özgeçmiş metni veriliyor.
Görevin, ilan eşleştirmesinde kullanılacak yapılandırılmış bir aday profili çıkarmak.

Kurallar:
- Sadece CV'de yazana dayan. Bilgi yoksa alanı boş bırak; uydurma.
- Deneyim yılını iş tarihlerinden hesapla; çakışan dönemleri bir kez say.
- Yetkinlikleri normalize et ("React.js" ve "ReactJS" -> "React"), tekrar etme.
- target_titles alanına adayın gerçekten alabileceği pozisyonları yaz;
  bir kademe yukarısı makulse ekle, iki kademe yukarısını ekleme.
- summary alanını Türkçe yaz, geri kalan liste alanlarını CV'deki dille bırak
  (teknoloji adları her zaman İngilizce).
- Metin bir PDF'ten çıkarıldığı için satır sırası yer yer bozuk olabilir;
  bağlamdan doğru okumayı çıkar, anlamsız parçaları görmezden gel.

Yalnızca istenen JSON'u üret, başka açıklama yazma."""


async def parse_cv(filename: str, data: bytes) -> CandidateProfile:
    text = to_text(filename, data)
    prompt = f"Bu özgeçmişten aday profilini çıkar.\n\n--- CV BAŞLANGIÇ ---\n{text}\n--- CV BİTİŞ ---"
    return await structured(schema=CandidateProfile, system=SYSTEM, prompt=prompt)
