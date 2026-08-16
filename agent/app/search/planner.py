"""Aday profili + kullanıcı kriterleri -> arama planı."""

from __future__ import annotations

import json

from ..llm import structured
from ..schemas import CandidateProfile, SearchCriteria, SearchPlan

SYSTEM = """Sen bir iş arama stratejistisin. Elinde bir aday profili ve adayın
kriterleri var. Görevin, iş ilanı API'lerine gönderilecek bir arama planı üretmek.

Bu planı ilan siteleri kullanacak, dolayısıyla:
- Sorgular KISA ve GENEL olmalı (1-3 kelime). "senior python backend developer with
  kubernetes experience" değil, "python backend" ve "django" gibi.
- Sorguları çeşitlendir: bir unvan üzerinden, bir çekirdek teknoloji üzerinden,
  bir de alan/domain üzerinden ara. Hepsi aynı şeyi aramasın.
- Sorgular İngilizce olmalı; ilan havuzlarının çoğu İngilizce.
- must_have_skills'e adayın gerçekten sahip olduğu ve pozisyonun çekirdeği olan
  yetkinlikleri koy. Adayda olmayan bir şeyi zorunlu yapma.
- exclude_terms'e adayın seviyesinin çok üstü/altı veya alakasız alan terimlerini
  koy (ör. junior bir aday için "principal", "director"; backend'ci için "sales").
- locations'a kriterlerdeki şehir/ülkeleri yaz; uzaktan çalışma açıksa "remote" ekle.

Yalnızca istenen JSON'u üret, başka açıklama yazma."""


async def build_plan(profile: CandidateProfile, criteria: SearchCriteria) -> SearchPlan:
    payload = {
        "aday_profili": profile.model_dump(),
        "kriterler": criteria.model_dump(),
    }
    prompt = (
        "Aşağıdaki profil ve kriterlere göre arama planını üret.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
    return await structured(schema=SearchPlan, system=SYSTEM, prompt=prompt)
