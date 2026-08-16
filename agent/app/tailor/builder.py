"""İlana özel CV + ön yazı üretimi.

Tasarımın merkezindeki kısıt: **yeni bilgi uydurulmaz.** Model yalnızca
profildeki gerçekleri ilanın diline yeniden çerçeveler. Bunun iki nedeni var:
1. Yalan beyanla alınan mülakat teknik soruda çöker; kullanıcıya zarar verir.
2. Bir başvuru geri alınamaz — uydurma bir satır CV'de kaldığı sürece risk.

Şeffaflık için model neyi öne çıkardığını (`emphasized`), neyi geri plana
attığını (`downplayed`) ve kapatılamayan eksikleri (`gaps_to_expect`) ayrıca
raporluyor; arayüz bunları kullanıcıya gösteriyor ki ne imzaladığını bilsin.
"""

from __future__ import annotations

import json

from ..llm import structured
from ..schemas import ApplicationKit, CandidateProfile, JobPosting

SYSTEM = """Sen deneyimli bir kariyer koçu ve teknik işe alım uzmanısın. Sana bir
adayın profili ve başvurmak istediği bir iş ilanı veriliyor. Bu ilana özel bir
CV ve ön yazı hazırlayacaksın.

MUTLAK KURAL — UYDURMA YOK:
- Profilde olmayan hiçbir teknoloji, deneyim, şirket, eğitim, sertifika veya
  rakam ekleme. Tek bir tane bile.
- Deneyim süresini uzatma, unvanı yükseltme, şirket adını değiştirme.
- İlan bir şey istiyor ve adayda yoksa, onu CV'ye YAZMA. gaps_to_expect
  alanına yaz ki aday mülakata hazırlıklı gitsin.
- Profildeki bir maddeyi ilanın diline çevirmek serbesttir; olmayan bir şeyi
  "benzer" diye eklemek değildir.

NE YAPACAKSIN:
- İlanın aradığı yetkinliklerle örtüşen deneyimleri öne çıkar, sıralamayı
  ona göre yap.
- İlanın kullandığı terimleri kullan (aday "REST API" yazmış, ilan "RESTful
  services" diyorsa ikincisini kullanabilirsin — aynı şeyi anlatıyorlar).
- Alakasız deneyimleri kısalt, tamamen silme.
- Madde başlarını somut yaz: ne yaptı, hangi ölçekte, sonuç neydi. Rakam
  varsa profilden al; yoksa rakam uydurma.
- ATS taramalarını düşün: ilanın anahtar terimleri doğal biçimde geçsin,
  ama anahtar kelime yığını yapma.

DİL:
- Kit'in dili ilanın diliyle aynı olmalı. İlan Türkçeyse her şey Türkçe,
  İngilizceyse her şey İngilizce. language alanına 'tr' ya da 'en' yaz.
- Teknoloji adları her iki dilde de İngilizce kalır.

ÖN YAZI:
- 4-6 paragraf, kısa tut. "Bu pozisyona başvurmak istiyorum çünkü şirketiniz
  sektörün öncüsü" gibi klişe açılış YAPMA.
- İlk paragrafta neden bu rol için uygun olduğunu somut bir örnekle söyle.
- Şirket hakkında bilmediğin şeyi övme; ilan metninde ne yazıyorsa ona dayan.

Yalnızca istenen JSON'u üret, başka açıklama yazma."""


async def build_kit(profile: CandidateProfile, job: JobPosting) -> ApplicationKit:
    prompt = (
        "ADAY PROFİLİ (tek gerçek kaynak — buradaki bilgiler dışına çıkma):\n"
        + json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)
        + "\n\nBAŞVURULACAK İLAN:\n"
        + job.digest(max_chars=6000)
        + "\n\nBu ilana özel CV ve ön yazıyı hazırla."
    )
    return await structured(
        schema=ApplicationKit,
        system=SYSTEM,
        prompt=prompt,
        # Kit üretimi tek seferlik ve uzun çıktılı; skorlamadan daha cömert süre
        timeout=420,
    )
