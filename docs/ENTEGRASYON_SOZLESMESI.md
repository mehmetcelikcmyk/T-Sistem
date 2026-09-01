# 🔌 T-Sistem — Entegrasyon Sözleşmesi (Modül Arayüz Kontratı)

> **Bu doküman neden var?**
> Ekip üyeleri modüllerini paralel geliştiriyor ve entegrasyon en sona bırakıldı.
> Bu doğru bir plan — ama yalnızca **arayüzler baştan sabitlenmişse** işe yarar.
> Aksi hâlde herkesin kodu tek başına çalışır, birleştirme günü hiçbiri birbirine
> takılmaz ve bitmiş işler yeniden yazılır.
>
> Aşağıdaki tablolar, her fonksiyonun **tam olarak hangi alan adlarıyla ne
> döndüreceğini** belirler. Bu, öneri değil **kontrat**tır:
> `tests/test_contracts.py` bu kontratı otomatik doğrular. Bir alan adı
> değişirse test **kırmızıya döner** — hatayı entegrasyon gününde değil, o
> commit'te görürsün.

**Kontratı doğrula:**
```bash
pytest tests/test_contracts.py -v
```

---

## 📐 Temel Kurallar

1. **Alan adları değiştirilemez.** İçerik/değer serbest, anahtar isimleri sabit.
2. **`None` yerine boş değer döndür.** Liste bekleniyorsa `[]`, metin bekleniyorsa `""`.
3. **Exception fırlatma, hata alanı doldur.** İskeletler `success` / `error`
   alanı taşıyorsa hatayı oraya yaz; API katmanı bunu 422 yanıtına çevirir.
4. **Eşik ve risk kararları modül sahibinde değil, tek yerdedir.** Örneğin
   benzerlik riskini Birhan değil, `summarize_similarity()` belirler.
5. **Bir alanı gerçekten değiştirmen gerekiyorsa** önce `src/api/schemas.py`
   içindeki şemayı güncelle, sonra testi çalıştır, sonra ekibe haber ver.
   Sırayı bozma.

---

## 🟢 BİRHAN — Veri Pipeline, NLP, Kural Motoru

### 1. `src/ingestion/pdf_loader.py` → `load_pdf()`

> ⚠️ **İmza değişti:** Fonksiyon eskiden `pdf_path: str` alıyordu. API katmanı
> yüklenen dosyayı diske yazmıyor (`await file.read()` ile bellekte tutuyor),
> yani çağrı anında bir dosya yolu **yok**. Artık bayt alıyor.
> PyMuPDF ve pdfplumber ikisi de bellekten okur:
> `fitz.open(stream=file_bytes, filetype="pdf")` /
> `pdfplumber.open(io.BytesIO(file_bytes))`

```python
def load_pdf(file_bytes: bytes, filename: str = "rapor.pdf") -> dict
```

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `filename` | `str` | Özgün dosya adı |
| `total_pages` | `int` | Sayfa sayısı |
| `raw_text` | `str` | Tüm sayfaların birleştirilmiş metni |
| `pages` | `list[dict]` | `{"page_number": int, "text": str}` |
| `tables` | `list` | Ayrıştırılan tablolar (opsiyonel) |
| `success` | `bool` | Ayrıştırma başarılı mı |
| `error` | `str \| None` | Başarısızsa **Türkçe** hata açıklaması |

### 2. `src/ingestion/preprocessor.py` → `chunk_text()`

```python
def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]
```
Boş metinde `[]` döndür.

### 3. `src/checkers/language_checker.py` → `check_language()`
**Şema:** `LanguageCheckResult`

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `detected_lang` | `str` | `"tr"` \| `"en"` |
| `expected_lang` | `str` | Şartnamenin istediği dil |
| `is_valid` | `bool` | `detected_lang == expected_lang` |
| `confidence` | `float` | 0.0 – 1.0 |

### 4. `src/checkers/template_checker.py` → `check_template()`
**Şema:** `TemplateCheckResult` · ⚠️ **İmza `bytes` aldı** (yukarıdaki gerekçe)

```python
def check_template(file_bytes: bytes, max_pages: int = 15, filename: str = "rapor.pdf") -> dict
```

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `page_count` | `int` | Tespit edilen sayfa sayısı |
| `max_allowed` | `int` | Şartname sınırı |
| `is_valid` | `bool` | Sınır aşılmadı ve uyarı yok |
| `font_family_detected` | `str \| None` | ör. `"Arial (11pt)"` |
| `warnings` | `list[str]` | Hakeme gösterilecek **Türkçe** uyarılar |

### 5. `src/checkers/section_checker.py` → `check_sections()`
**Şema:** `SectionCheckResult`

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `total_required` | `int` | Kontrol edilen zorunlu başlık sayısı |
| `found_count` | `int` | `status == "OK"` olan bölüm sayısı |
| `is_complete` | `bool` | `found_count == total_required` |
| `sections` | `dict[str, dict]` | Anahtar → bölüm durumu (aşağıda) |

**`sections` sözlüğünün her elemanı:**

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `section_name` | `str` | Görünen başlık adı |
| `exists` | `bool` | Başlık raporda bulundu mu |
| `word_count` | `int` | Başlık altındaki kelime sayısı |
| `status` | `str` | **Yalnızca** `"OK"` \| `"EMPTY"` \| `"MISSING"` |

**Sabit bölüm anahtarları** (frontend bunlara göre rozet basar, değiştirilemez):
`ozet` · `problem` · `yontem` · `ozgunluk` · `uygulanabilirlik` · `kaynaklar`

> Durum etiketini elle hesaplama: `classify_section(exists, word_count)`
> yardımcısını çağır. Eşik (`MIN_WORDS_PER_SECTION = 50`) tek yerde durur.

### 6. `src/checkers/category_checker.py` → `check_category_alignment()`
**Şema:** `CategoryCheckResult`

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `applied_category` | `str` | Başvurulan kategori adı |
| `is_aligned` | `bool` | `semantic_similarity >= 0.60` |
| `semantic_similarity` | `float` | 0.0 – 1.0 |
| `explanation` | `str` | Hakeme gösterilecek **Türkçe** gerekçe |

### 7. `src/similarity/vector_store.py` → `find_similar_reports()`

```python
def find_similar_reports(self, query_text: str, top_k: int = 3, threshold: float = 0.70) -> list[dict]
```

**Listenin her elemanı** (`SimilarProjectMatch` şeması):

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `matched_report_id` | `str` | Eşleşen raporun ID'si |
| `project_title` | `str` | Eşleşen projenin adı |
| `similarity_ratio` | `float` | 0.0 – 1.0 kosinüs benzerliği |
| `matched_paragraphs` | `list[str]` | Hakeme gösterilecek alıntılar |

> 🔸 **Risk seviyesini sen hesaplamıyorsun.** Yalnızca eşleşme listesini
> döndür. `risk_level`, `is_high_risk` ve `highest_similarity` alanlarını
> `summarize_similarity(matches)` üretir. Eşikler orada, tek yerde:
> **HIGH ≥ 0.70** · **MEDIUM ≥ 0.40** · aksi hâlde **LOW**.
> Eşleşme yoksa `[]` döndür, `None` döndürme.

### 8. `src/similarity/embeddings.py` → `get_embeddings()`

```python
def get_embeddings(texts: list[str]) -> list[list[float]]
```
Tüm vektörler aynı boyutta olmalı (`paraphrase-multilingual-MiniLM-L12-v2` → 384).

---

## 🟣 EMRE — Frontend

Frontend'in bağlanacağı tüm alanlar aşağıdaki endpoint'lerde sabittir.
**Canlı ve her zaman güncel referans:** `http://localhost:8000/docs`

| Endpoint | Metot | Ne döndürür |
| :--- | :--- | :--- |
| `/api/reports/upload` | POST | `ReportUploadResponse` — `report_id`, `storage_backend`, `security_risk_level` |
| `/api/reports/{id}/analysis` | GET | `ComprehensiveReportAnalysisResponse` — hakem panelinin tamamı |
| `/api/referee/evaluate` | POST | `RefereeDecisionResponse` — nihai karar kaydı |
| `/api/referee/chat` | POST | `RefereeChatResponse` — AI asistan yanıtı |
| `/api/contestant/feedback/{id}` | GET | `ContestantFeedbackResponse` — yarışmacı karnesi |
| `/api/admin/metrics` | GET | `AdminMetricsResponse` — dashboard metrikleri (veritabanından canlı) |
| `/health` | GET | Sistem durumu ve LLM anahtar havuzu boyutu |

> ⚠️ **Önemli davranış:** Raporlar artık veritabanında tutuluyor. Var olmayan bir
> `report_id` ile `analysis` / `feedback` / `evaluate` çağırmak **404** döner
> (eskiden sahte veri üretiliyordu). Frontend akışı **önce upload → dönen
> `report_id` ile devam** şeklinde kurulmalı.

### `upload` çağrısının form alanları

| Alan | Zorunlu | Varsayılan |
| :--- | :--- | :--- |
| `file` | ✅ | — (yalnızca gerçek PDF; magic bytes doğrulanır, en fazla 30 MB) |
| `category` | ✖️ | `"Yapay Zekâ ve Otonom Sistemler"` |
| `project_name` | ✖️ | `"İsimsiz Proje"` |

Geçersiz dosya → **400** (`"Dosya gerçek bir PDF dokümanı değildir…"` gibi Türkçe mesaj).

### `security_check` bloğu (hakem panelinde kırmızı bayrak)

`analysis` yanıtındaki yeni alan — `SecurityCheckResult`:

| Alan | Tip | Açıklama |
| :--- | :--- | :--- |
| `file_validated` | `bool` | Dosya PDF doğrulamasını geçti mi |
| `injection_detected` | `bool` | Yapay zekâyı yönlendirme girişimi var mı |
| `injection_patterns` | `list[str]` | Tespit edilen ifadeler — **hakeme göster** |
| `pii_masked` | `dict[str,int]` | `{"tckn": 1, "phone": 0, "email": 2}` |
| `risk_level` | `str` | `LOW` / `MEDIUM` / `HIGH` |
| `notes` | `list[str]` | Hazır Türkçe açıklamalar — doğrudan bas |

> `injection_detected: true` ise hakem panelinde belirgin bir uyarı gösterilmeli:
> şüpheli ifadeler değerlendirmeye girmeden metinden çıkarıldı, ama hakem bunu
> bilmeli. `risk_level: HIGH` → 🔴, `MEDIUM` → 🟡, `LOW` → 🟢.

### Hata yanıtı formatı (tüm endpoint'ler için ortak)

Doğrulama hatası — **HTTP 422**:
```json
{
  "basarili": false,
  "hata_kodu": "DOGRULAMA_HATASI",
  "mesaj": "Gönderdiğiniz veriler doğrulanamadı. Lütfen aşağıdaki alanları kontrol edin.",
  "detaylar": [
    { "alan": "final_score", "mesaj": "Değer en fazla 100.0 olabilir.", "hata_tipi": "less_than_equal" }
  ]
}
```

HTTP hatası (400/404/…) ve sunucu hatası (500):
```json
{ "basarili": false, "hata_kodu": "HTTP_400", "mesaj": "Geçersiz dosya formatı. Yalnızca .pdf formatı desteklenir." }
```

> Frontend hata gösterimini `detaylar[].alan` → ilgili input alanı eşlemesi
> üzerine kur; mesajlar **hazır Türkçe** gelir, çeviri yapma.

### Rozet/renk mantığı için sabit değerler

| Alan | Olası değerler | Önerilen renk |
| :--- | :--- | :--- |
| `section_check.sections[].status` | `OK` / `EMPTY` / `MISSING` | 🟢 / 🟡 / 🔴 |
| `similarity_check.risk_level` | `LOW` / `MEDIUM` / `HIGH` | 🟢 / 🟡 / 🔴 |
| `security_check.risk_level` | `LOW` / `MEDIUM` / `HIGH` | 🟢 / 🟡 / 🔴 |
| `ai_evaluation.referee_recommendation` | `KABUL` / `REVİZYON` / `RET` | 🟢 / 🟡 / 🔴 |
| `overall_status` | `READY_FOR_REFEREE` / `EVALUATION_COMPLETED` | — |
| `decision` (evaluate isteği) | `APPROVED` / `REJECTED` / `NEEDS_REVISION` | 🟢 / 🔴 / 🟡 |

---

## 🔵 MEHMET — Entegrasyon Katmanı (bu tarafta kalan iş)

Aşağıdakiler **ekip üyelerini beklemez**, API katmanının kendi işidir:

- [x] `SecurityGuard`'ı `upload_report`'a bağla — dosya doğrulama, injection etkisizleştirme, KVKK maskeleme
- [x] `DatabaseManager` + depolamayı bağla — raporlar artık SQLite/D1'de, PDF'ler R2 veya `data/raw/`'da
- [x] `/api/admin/metrics`'i veritabanından hesapla
- [ ] `/api/reports/{id}/analysis` içindeki sabit blokları checker çağrılarıyla değiştir
      (iskeletler şema-uyumlu değer döndürüyor; bağlamak bugün güvenli)
- [ ] Yarışmacı karnesi için PDF/Markdown indirme endpoint'i (Issue #6 kabul kriteri)
- [ ] Rol bazlı erişim kontrolü (PRD'de 4 rol tanımlı)

### Yükleme hattının güvenlik sırası (değiştirilmemesi gereken sıra)

```
1. validate_file_safety()        # uzantı + PDF magic bytes + 30 MB sınırı
2. load_pdf(bytes)               # metin çıkarma (hata olursa akış durmaz)
3. neutralize_prompt_injection() # şüpheli talimatlar metinden ÇIKARILIR
4. anonymize_kvkk_data()         # TCKN / telefon / e-posta maskelenir
5. storage.upload_file_bytes()   # R2 veya data/raw/
6. evaluate_report_with_ai()     # LLM'e YALNIZCA temizlenmiş metin gider
7. db.save_report()              # kalıcı kayıt
```

> 3. ve 4. adım 6. adımdan **önce** olmalı. Tersine çevrilirse rapor içine
> gömülü "bu projeye 100 ver" gibi talimatlar doğrudan modele ulaşır.
> Hakem notu da depolanmadan önce `sanitize_input()` ile XSS'e karşı temizlenir.

---

## ✅ Entegrasyon Günü Kontrol Listesi

```bash
# 1. Kontrat hâlâ geçerli mi?
pytest tests/test_contracts.py -v

# 2. Regresyon var mı?
pytest -v

# 3. Sistem ayakta ve LLM bağlı mı?
uvicorn src.main:app --reload
curl http://localhost:8000/health     # llm_key_pool_size > 0 olmalı
```

Üçü de yeşilse entegrasyon mekanik bir işe iner: iskeletlerin gövdesini
gerçek implementasyonla değiştirmek. Arayüzler zaten uyuyor.
