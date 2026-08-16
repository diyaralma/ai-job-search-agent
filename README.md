# AI İş Arama Ajanı

CV yükle → kriterlerini belirle → ajan açık iş ilanı kaynaklarını ve şirketlerin
kendi başvuru panolarını tarayıp ilanları sana uygunluğuna göre skorlasın.

**Durum:** Arama + ilana özel CV/ön yazı üretimi çalışır durumda.

---

## Model sağlayıcısı: kendi LLM'ini kullan

Uygulama belirli bir modele bağlı değil. `agent/.env` içindeki tek bir satır
(`LLM_PROVIDER`) hangi motorun kullanılacağını belirler:

| `LLM_PROVIDER` | Ne gerekir | Kime uygun |
|---|---|---|
| `claude_cli` (varsayılan) | Claude Code kurulu + giriş yapılmış | Claude Pro/Max üyeliği olan — **API anahtarı ve kredi gerekmez** |
| `anthropic` | `ANTHROPIC_API_KEY` | Sunucuda/konteynerde çalıştıracak olan |
| `openai` | `LLM_MODEL` + (çoğu uçta) API anahtarı | OpenAI, OpenRouter, Groq, Together, DeepSeek, Google'ın OpenAI uçu, **Ollama / LM Studio / vLLM ile tamamen yerel** |

```bash
# Örnek 1 — OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Örnek 2 — tamamen yerel, anahtarsız, ücretsiz (Ollama)
LLM_PROVIDER=openai
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://localhost:11434/v1

# Örnek 3 — OpenRouter üzerinden herhangi bir model
LLM_PROVIDER=openai
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-...
```

Seçimini doğrula: `cd agent && ./.venv/bin/python scripts/check_llm.py`.
Sağlayıcının hazır olup olmadığı `http://localhost:3001` sayfasının başlığında
da yazar; eksik bir şey varsa ne yapılacağını söyleyen bir uyarı çıkar.

**Tasarım notu — şema garantisi sağlayıcıdan bağımsız.** Pipeline'ın her adımı
Pydantic şemasına uyan bir yanıt bekliyor. Her sağlayıcı elindeki en güçlü aracı
kullanıyor (Claude Code'da `--json-schema`, Anthropic API'de structured outputs,
OpenAI-uyumlu uçlarda `response_format`), dönen metin **her hâlükârda**
`app/llm.py` içinde Pydantic ile doğrulanıyor. Şema desteklemeyen bir yerel
sunucuda `LLM_JSON_MODE=auto` sırayla daha zayıf kiplere düşüyor ve çalışan kipi
hatırlıyor — zayıf bir model şemayı tutturamazsa hata net oluyor, sessizce bozuk
veri geçmiyor.

### Sağlayıcıya göre değişenler

- **`claude_cli`** — Çağrılar üyelik kullanım limitine sayılır, token başına
  ücret yok. Bir arama ≈ 6 çağrı (1 plan + 4 skorlama partisi + CV analizi 1).
  Her çağrı ayrı bir subprocess ve ~16k token sabit ek yük taşıdığı için
  maliyet yerine **duvar saati** optimize ediliyor: küçük partiler, yüksek
  paralellik. Docker'da çalışmaz — konteynerin içinde Claude Code oturumu yok.
- **`anthropic` / `openai`** — Her çağrı ücretli (yerel sunucular hariç), Docker
  ve sunucu dağıtımı sorunsuz. Ücretli bir sağlayıcıda `LLM_SCORE_LIMIT`
  değerini düşürmek doğrudan tasarruf: LLM'e giden ilan sayısını azaltır.

---

## Nasıl çalışır

```
CV (PDF/DOCX/TXT)
  └─> metin çıkarımı (yerel)                     agent/app/cv/
        └─> [LLM] CandidateProfile
              └─> [LLM] SearchPlan (sorgular, unvanlar, zorunlu yetkinlikler)
                    └─> kaynaklardan paralel toplama    agent/app/sources/
                          └─> tekilleştirme + sert filtreler (kural)
                                └─> ön sıralama + kaynak kotası (kural) → 32 ilan
                                      └─> [LLM] uygunluk skorlaması (4 paralel parti)
                                            └─> sıralı sonuç + gerekçe
```

İki aşamalı eleme bilinçli: kaynaklardan yüzlerce ilan geliyor, hepsini modele
göndermek hem yavaş hem gereksiz. Kural katmanı belirgin uyumsuzları eliyor,
LLM sadece gerçek karar gerektiren ilanlara bakıyor.

**Kaynak kotası** neden var: ATS panoları çok daha uzun ilan metni döndürüyor,
bu onlara ön elemede yapısal avantaj veriyor. Sınır olmadan takip edilen birkaç
şirket tüm sonuçları dolduruyor ve diğer kaynaklardaki uygun ilanlar hiç
değerlendirilmiyor. Tek kaynak LLM bütçesinin en fazla yarısını alabilir.

### Neden bu kaynaklar

| Kaynak | Anahtar | Kapsam | Coğrafi kısıt verisi |
|---|---|---|---|
| Remotive | — | Uzaktan çalışma ilanları | metin |
| Jobicy | — | Uzaktan çalışma ilanları | **yapılandırılmış** (`jobGeo`) |
| Himalayas | — | Uzaktan çalışma ilanları | **yapılandırılmış** (`locationRestrictions`) |
| RemoteOK | — | Uzaktan çalışma ilanları | metin |
| Arbeitnow | — | Avrupa, ağırlıklı Almanya | metin |
| Greenhouse / Lever / Ashby / Workable | — | Şirketlerin **kendi** başvuru panoları | metin |
| Adzuna | ücretsiz tier | ABD, İngiltere, Almanya, +14 ülke | metin |
| Jooble | ücretsiz | Türkiye dahil geniş coğrafya | metin |

Jobicy ve Himalayas'ın coğrafi kısıtı yapılandırılmış vermesi önemli: "Remote —
United States" ilanının Türkiye'deki adaya gösterilmemesi tahmine değil, veriye
dayanıyor.

### LinkedIn ve Indeed neden yok

İkisinin de bu iş için açık API'si yok — LinkedIn'in İş İlanları API'si yalnızca
anlaşmalı ATS sağlayıcılarına veriliyor, Indeed halka açık yayıncı API'sini yeni
başvurulara kapattı. Geriye kazıma kalıyor; o da kullanım sözleşmesini ihlal
ediyor, aktif olarak engelleniyor (giriş duvarı, bot tespiti) ve hesap
kısıtlamasına yol açabiliyor.

Bu ilanlara meşru zeminde ulaşmak istiyorsan yol **Google Jobs / SerpAPI**:
Google'ın indeksi üzerinden LinkedIn ve Indeed ilanlarını da kapsıyor, aylık
~50$ civarı ücretli. Eklemek istersen `agent/app/sources/` altına yeni bir
kaynak sınıfı yeterli — arayüz ve pipeline değişmiyor.

---

## Kurulum

### Gereksinimler
- Python 3.12+, Node.js 20+
- Bir model sağlayıcısı (yukarıdaki tablo). Varsayılan `claude_cli` için Claude
  Code kurulu ve giriş yapılmış olmalı (`claude --version` çalışmalı);
  kullanmıyorsan `agent/.env` içinde `LLM_PROVIDER` değerini değiştir.

### Hızlı başlangıç

```bash
cd agent
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env                       # sağlayıcını seç: LLM_PROVIDER=...
./.venv/bin/python scripts/check_llm.py    # model erişimini doğrula
cd .. && (cd web && npm install)

./start.sh    # agent :8000, web :3001
./stop.sh     # durdurmak için
```

`python3 -m venv` çalışmazsa (Debian/Ubuntu'da `python3-venv` paketi eksik olabilir):

```bash
sudo apt install python3-venv python3-pip     # ya da sudo gerektirmeyen yol:
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv venv .venv && ~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
```

Web arayüzü **3001** portunda çalışır (3000 çoğu makinede başka bir şeyle dolu).
Farklı port kullanacaksan `agent/.env` içindeki `CORS_ORIGINS` değerine o adresi
eklemeyi unutma. `stop.sh` yalnızca `start.sh`'ın başlattığı süreç gruplarını
durdurur, makinedeki başka Next.js/uvicorn uygulamalarına dokunmaz.

---

## Kullanım

`./start.sh` sonrası tarayıcıda **http://localhost:3001**. Başlığın altında hangi
sağlayıcı ve modelin aktif olduğu yazar: nokta yeşilse hazır, sarıysa neyin eksik
olduğunu (CLI, anahtar, model adı) orada söyler.

### 1. CV yükle

PDF, DOCX veya TXT — en fazla 25 MB, sürükle-bırak çalışır.

Metin yerelde çıkarılıyor (pypdf / python-docx), sonra modele gidip yapılandırılmış
profile dönüşüyor: hedef unvanlar, yetkinlikler, deneyim yılı, seviye, diller,
eğitim. **10-25 saniye** sürer, sonucu ekranda görürsün. Seviye ya da unvanlar
alakasız çıktıysa PDF'in okunma sırası bozulmuş olabilir (ağır tasarımlı/iki
kolonlu dosyalarda olur) — aynı CV'yi DOCX olarak yükle.

Profil tarayıcıda saklanıyor: sayfayı yenileyince CV'yi tekrar yüklemen gerekmez.
Başka bir CV denemek için profil kartındaki **"Farklı CV yükle"** düğmesini kullan.

### 2. Kriterleri belirle

| Alan | Not |
|---|---|
| **Ülkeler / Şehirler** | Virgülle ayır (`Türkiye, Germany`). Boş bırakırsan coğrafi filtre uygulanmaz. |
| **Çalışma şekli** | Uzaktan / Hibrit / Ofisten. "Uzaktan"da ilanın **kendi** coğrafi kısıtı da kontrol edilir — "Remote — US only" ilanı Türkiye'deki adaya gösterilmez. |
| **Seviye** | Seçilmezse tüm seviyeler. |
| **Hariç tutulacak kelimeler** | İlan **başlığında** geçerse elenir (`sales, unpaid, commission`). |
| **Hariç tutulacak şirketler** | Eski işveren, görmek istemediğin şirketler. |
| **İlan yaşı (gün)** | Varsayılan 45. |
| **Sonuç sayısı** | Varsayılan 40. |

### 3. Ara ve sonuçları oku

Arama **30-90 saniye** sürüyor ve HTTP isteği boyunca açık kalıyor — sekmeyi
kapatma. Bu sürede sırasıyla: arama planı üretilir, kaynaklar paralel taranır,
kural katmanı eleme yapar, kalan ilanlar modele skorlatılır.

Sonuç başlığındaki dört sayı akışı gösterir: **çekilen → tekilleştirme sonrası →
ön elemeyi geçen → yapay zekâ skorlaması**. Aradaki büyük düşüş normaldir; kural
katmanı belirgin uyumsuzları eliyor.

Her kartta skor (0-100), karar etiketi (`strong` / `good` / `stretch` / `poor`),
eşleşen ve eksik görünen yetkinlikler, skorun Türkçe gerekçesi ve varsa
başvuru öncesi riskler var. İki uyarı çıkabilir:

- **"Kriterlerinize uyan ilan havuzu dar"** — filtreyi çok az ilan geçti,
  kriterleri gevşetmeyi ya da ilan yaşını artırmayı dene.
- **"Kriterlerinize uyan ilan bulunamadı"** — hiç kalmadığı için filtreler
  otomatik gevşetildi; gördüğün sonuçlar kriterlerinin dışında olabilir.

### 4. İlana özel CV ve ön yazı üret

Beğendiğin ilanın kartındaki **"İlana özel CV hazırla"** düğmesi o ilana özel bir
kit üretir (**20-40 saniye**): uyarlanmış CV (**PDF** ve **DOCX** indirilebilir),
ilanın dilinde ön yazı, "Neden ben?" cevabı, vurgulanacak maddeler ve şeffaflık
bölümü. Metin alanlarının yanındaki **Kopyala** düğmesiyle doğrudan başvuru
formuna yapıştırabilirsin.

Model profilindeki gerçekleri yalnızca yeniden çerçeveler; olmayan bir deneyimi
CV'ye yazmaz, "mülakatta sorulabilir" başlığı altında listeler
([Uydurma yok](#uydurma-yok--tasarımın-merkezindeki-kısıt) bölümüne bak).

### 5. Başvur

Kart üzerindeki bağlantı seni ilanın kendi sayfasına götürür — başvuru her zaman
ilan sahibinin sistemi üzerinden yapılır, uygulama senin adına form doldurmaz
([neden](#otomatik-başvuru-neden-yok)).

Bitince `./stop.sh`.

### Bir aramanın maliyeti

Bir arama ≈ **6 model çağrısı** (1 plan + 4 skorlama partisi + kit için 1;
CV analizi ayrıca 1). `claude_cli` sağlayıcısında bu üyelik kullanım limitine
sayılır, token ücreti yoktur. Ücretli bir sağlayıcıdaysan en büyük kalem
skorlamadır: `LLM_SCORE_LIMIT` değerini düşürmek (ör. 32 → 16) doğrudan yarıya
indirir, karşılığında daha az ilan değerlendirilir.

### Sık karşılaşılanlar

| Belirti | Ne yapmalı |
|---|---|
| Başlıkta sarı nokta / sarı uyarı kutusu | Sağlayıcı hazır değil. `cd agent && ./.venv/bin/python scripts/check_llm.py` net hatayı verir. |
| `Model çıktısı şemaya uymadı` | Model şemayı tutturamıyor — genelde küçük yerel modellerde. Daha büyük bir model dene ya da `LLM_JSON_MODE=object` (bazı sunucularda `prompt`). |
| `Yanıt LLM_MAX_TOKENS sınırında kesildi` | `LLM_MAX_TOKENS` değerini artır ya da `SCORE_BATCH_SIZE`'ı küçült. |
| Hız/kota sınırı (429) | `MAX_CONCURRENCY` değerini düşür. |
| Sonuçlarda Türkiye ilanı yok | Anahtarsız kaynakların hiçbiri Türkiye yerel ilanı taşımıyor; `JOOBLE_HOST=https://tr.jooble.org` + o bölgeden alınmış `JOOBLE_API_KEY` gerekir. |
| "Agent servisine ulaşılamadı" | `tail -30 /tmp/jobagent-agent.log` — servis çökmüş olabilir. |
| 3001 portu dolu | Web'i başka portta çalıştırıp `agent/.env` içindeki `CORS_ORIGINS` değerine o adresi ekle. |

---

## Doğrulama scriptleri

```bash
cd agent
./.venv/bin/python scripts/test_prefilter.py   # kural katmanı birim testleri (LLM'siz, saniyeler)
./.venv/bin/python scripts/smoke_sources.py    # kaynaklar canlı mı (LLM'siz)
./.venv/bin/python scripts/smoke_pipeline.py   # tüm pipeline (LLM taklit edilir)
./.venv/bin/python scripts/check_llm.py        # model erişimi (1 gerçek çağrı)
```

Bir kaynağın API'si değiştiğinde ilk bakılacak yer `smoke_sources.py`.
Eşleştirme mantığını değiştirdiysen `test_prefilter.py` — oradaki hatalar
ilanları elemez, sadece yanlış sıralar ve fark etmesi zordur.

---

## Yapılandırma

`agent/.env` içindeki başlıca ayarlar:

| Değişken | Varsayılan | Ne işe yarar |
|---|---|---|
| `LLM_PROVIDER` | `claude_cli` | `claude_cli` / `anthropic` / `openai` |
| `LLM_MODEL` | sağlayıcıya göre | Model adı; `openai` sağlayıcısında zorunlu |
| `LLM_API_KEY` | — | Anahtar; `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` de okunur |
| `LLM_BASE_URL` | — | OpenAI-uyumlu uç adresi (çoğunda sonu `/v1`) |
| `LLM_TIMEOUT` | `300` | Tek model çağrısının saniye sınırı |
| `LLM_MAX_TOKENS` | `16000` | Tek yanıtın token tavanı ("kesildi" hatasında artır) |
| `LLM_JSON_MODE` | `auto` | Şema zorlama kipi (yalnızca `openai`): `auto`/`schema`/`object`/`prompt` |
| `LLM_SCORE_LIMIT` | `32` | Kaç ilan LLM'e gider (ücretli sağlayıcıda ana maliyet kalemi) |
| `SCORE_BATCH_SIZE` | `8` | Tek çağrıda kaç ilan skorlanır |
| `MAX_CONCURRENCY` | `4` | Kaç parti aynı anda çalışır |
| `JOOBLE_HOST` | `https://jooble.org` | Anahtarın alındığı bölge; TR için `https://tr.jooble.org` |
| `ADZUNA_APP_ID/KEY`, `JOOBLE_API_KEY` | — | Boşsa o kaynak sessizce kapanır |

Üçlü (`32 / 8 / 4`) tek dalgada bitecek şekilde seçildi. Parti boyutunu
büyütmek çağrı sayısını azaltır ama her çağrıyı uzatır — süre üretilen token
sayısıyla orantılı olduğu için duvar saati kötüleşir.

### Takip edilecek şirketler

`agent/app/sources/companies.json` içine hedef şirketlerinin ATS pano kimliğini ekle.
Kimliği ilan URL'sinden çıkarabilirsin:

```
boards.greenhouse.io/<token>        jobs.lever.co/<company>
jobs.ashbyhq.com/<board>            <account>.workable.com
```

Çalışmayan bir kimlik sessizce atlanır, arama etkilenmez. **Dosyadaki liste
örnek amaçlı ve ABD merkezli** — kendi hedef şirketlerinle değiştir.

---

## Bilinen sınırlar

- **Türkiye ilanları Jooble anahtarına bağlı.** Anahtarsız kaynakların hiçbiri
  Türkiye yerel iş ilanlarını taşımıyor. Ölçüm — "Türkiye + Ankara/İstanbul"
  kriteriyle: anahtarsız 320 ilan çekiliyor ve Türkiye merkezli ilan **sıfır**;
  Jooble TR anahtarıyla 368 ilan ve sonuçların yarısı İstanbul/Ankara merkezli.
  **Jooble anahtarları bölgeseldir** — `jooble.org` anahtarı ABD indeksini
  sorgular ("Turkey" araması Kuzey Karolina'daki Turkey kasabasını getirir).
  Anahtarı `tr.jooble.org/api/about` üzerinden alıp `JOOBLE_HOST` değerini o
  adrese çevir. Varsayılan kota 500 istek; arama başına şehir sayısı kadar
  istek gider.
- **Arama senkron ve yavaş.** ~85 saniye sürüyor ve HTTP isteği boyunca açık
  kalıyor. Üretimde kuyruk + iş durumu sorgulama gerekir.
- **PDF metin çıkarımı yerel.** Modele `document` bloğu göndermek yerine
  (sağlayıcıların hepsi desteklemiyor) PDF'i pypdf ile metne çeviriyoruz. Tek kolonlu CV'lerde
  sorun yok; ağır tasarımlı/iki kolonlu PDF'lerde okuma sırası bozulabilir.
  Taranmış PDF'te açık hata veriyoruz — DOCX/TXT yükle.
- **Tek kullanıcı.** SQLite, kimlik doğrulama yok. Çok kullanıcı için
  Postgres + auth gerekir; `agent/app/store.py` bu geçiş düşünülerek yazıldı.
- **Maaş filtresi uygulanmıyor.** `min_salary` alınıyor ama ilanların çoğu
  maaşı yapılandırılmış vermediği için filtreye dönüştürülmedi; LLM ilan
  metninde görürse değerlendirmesine katıyor.

---

## Başvuru kiti (ilana özel CV)

Her sonucun altındaki **"İlana özel CV hazırla"** butonu, o ilana özel bir kit üretir:

- **Uyarlanmış CV** — PDF ve DOCX olarak indirilebilir
- **Ön yazı** — kopyalanabilir, ilanın dilinde
- **"Neden ben?" cevabı** ve **vurgulanacak maddeler**
- **Şeffaflık bölümü** — neyin öne çıkarıldığı, neyin geri plana atıldığı
- **"Mülakatta sorulabilir"** — ilanın istediği ama profilde olmayan şeyler

### Uydurma yok — tasarımın merkezindeki kısıt

Model yalnızca profildeki gerçekleri ilanın diline **yeniden çerçeveler**.
Olmayan bir teknoloji, deneyim, şirket veya rakam eklemez. İlan bir şey istiyor
ve adayda yoksa CV'ye yazılmaz; `gaps_to_expect` alanına yazılır ve arayüzde
sarı kutuda gösterilir.

Gerçek bir çıktıdan örnek: ilan GitHub Actions istiyordu, adayda genel CI/CD
deneyimi vardı. Kit CI/CD'yi "GitHub Actions gereksinimine en yakın eşleşme"
olarak öne çıkardı, ama GitHub Actions deneyimi olduğunu **iddia etmedi** —
onu eksikler listesine koydu.

Gerekçe basit: yalan beyanla alınan mülakat teknik soruda çöker ve gönderilen
bir başvuru geri alınamaz.

### Dil

Kit ilanın dilinde üretilir. CV bölüm başlıkları da ona göre değişir
(ÖZET/DENEYİM ya da SUMMARY/EXPERIENCE) — İngilizce bir CV'de Türkçe başlık
belgeyi bozuk gösterir.

### Otomatik başvuru neden yok

Otomatik form doldurma yalnızca şirketlerin kendi ATS panolarında
(Greenhouse/Lever/Ashby/Workable) güvenilir çalışır. Aracı sitelerden
(Jooble, Jobicy) gelen ilanlar tıklama takipli yönlendirmelerle rastgele
işveren sitelerine çıkıyor; bunlar programatik olarak çözülemiyor — HEAD
isteği bile 403 alıyor.

Bu yüzden akış "kit hazırla → ilana git → yapıştır ve gönder" şeklinde.
`companies.json` içine ATS panosu olan şirketler eklenirse ileride o ilanlar
için form doldurma eklenebilir.

## Dizin yapısı

```
agent/                     Python FastAPI agent servisi
  app/
    cv/                    CV → metin → CandidateProfile
    search/                planner (LLM) + prefilter (kural, kaynak kotası, coğrafi ceza)
    match/                 LLM skorlama, paralel partiler
    tailor/                ilana özel CV üretimi + PDF/DOCX render
    sources/               ilan kaynakları + companies.json
    providers/             model sağlayıcıları (claude_cli / anthropic / openai)
    pipeline.py            uçtan uca akış
    llm.py                 sağlayıcı seçimi + şema doğrulama (tek giriş noktası)
    text.py                normalizasyon + kelime sınırı eşleştirme
    store.py               SQLite
    schemas.py             tüm veri tipleri (API sözleşmesi dahil)
  scripts/                 doğrulama scriptleri
web/                       Next.js arayüz
  app/page.tsx             3 adımlı akış
  components/              yükleyici, kriter formu, sonuç kartları
  lib/types.ts             schemas.py'nin TS karşılığı
start.sh / stop.sh         iki servisi birlikte başlat/durdur
```

`agent/app/schemas.py` değiştiğinde `web/lib/types.ts` de güncellenmeli — ikisi
elle senkron tutuluyor.
