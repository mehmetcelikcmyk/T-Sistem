# T-SİSTEM · DERİN ANALİZ VE UYGULAMA PLANI (V6)

**Hazırlanma tarihi:** 24 Ağustos 2026
**Kapsam:** `C:\Users\mehme\OneDrive\Desktop\T-Sistem` kod tabanının tamamı (~430 KB Python, 60+ modül), `.gemini/antigravity-ide/brain` altındaki 294 kullanıcı mesajlık geçmiş konuşma, önceki `implementation_plan.md` ve `walkthrough.md`, `data/` altındaki migration planları ve yerel veritabanı.
**Yöntem:** 5 paralel derin kod denetimi (tema, yarışmacı, hakem, yönetici, veri katmanı) + geçmiş konuşmadan ister çıkarımı + yerel SQLite şema/veri doğrulaması.

---

## 0. YÖNETİCİ ÖZETİ — TEK CÜMLEYLE DURUM

> **Uygulamanın arayüzü %85 hazır, iş mantığı %40 hazır, veri katmanı %15 hazır.**
> Ekranların büyük kısmı çizilmiş; ancak **yazma işlemlerinin çoğu diske hiç ulaşmıyor** ve bu hatalar `except Exception: pass` blokları tarafından yutulup kullanıcıya `st.success("Başarıyla kaydedildi")` olarak gösteriliyor.

Bunun kanıtı, uygulamanın kendi veritabanıdır. `data/tsistem.db` şu an şu durumda:

| Tablo | Kayıt sayısı |
|---|---|
| `auth_users` | **2** (yalnızca seed admin + seed hakem) |
| `calibration_settings` | 8 (varsayılan seed) |
| `competitions` | **0** |
| `competition_stages` | **0** |
| `competition_rubrics` | **0** |
| `category_requirements` | **0** |
| `report_template_requirements` | **0** |
| `reports` | **0** |
| `categories`, `users` | **0** |

Yani bugün uygulamayı açıp admin olarak "Yeni Yarışma Oluştur" dediğinizde ekranda "başarılı" yazacak, ama tabloda hiçbir şey olmayacak. Bu, geçmiş konuşmadaki *"neden 65 yarışma D1'e aktarıldı dedin 60 kategori var"*, *"hâlâ demo veri var"*, *"bunları Cloudflare'a aktardın mı"* şikâyetlerinin **tek ortak kök nedenidir**.

### Bulguların ağırlık dağılımı

| Kategori | Kritik | Yüksek | Orta |
|---|---|---|---|
| Güvenlik | 4 | 3 | 2 |
| Veri katmanı / şema | 9 | 6 | 5 |
| Rol izolasyonu / yetki | 3 | 2 | 1 |
| Tema tutarlılığı | 1 | 4 | 12 |
| AI motoru | 3 | 5 | 4 |
| Demo/sahte veri | 5 | 8 | 10 |
| Ölü kod | — | 4 | 15 |

---

## 1. ⛔ ACİL — İŞE BAŞLAMADAN ÖNCE (0. GÜN)

Bu maddeler kod yazmadan önce, bugün yapılmalıdır.

### 1.1 Sızmış kimlik bilgileri (KRİTİK)

`.env` dosyası projenin içinde ve **canlı sırlar** içeriyor:

| Sır | Adet | Yetki |
|---|---|---|
| Cloudflare API Token (`cfut_...`) | 1 | D1 veritabanına tam okuma/yazma |
| Cloudflare R2 Access + Secret Key | 1 çift | Bucket'a tam erişim |
| Anthropic API anahtarı | 3 | Faturalandırılabilir kullanım |
| Groq API anahtarı | 3 | Faturalandırılabilir kullanım |
| OpenAI API anahtarı | 3 | Faturalandırılabilir kullanım |

Ayrıca **`src/ui/firebase_config.py:15`** içinde Google OAuth `clientSecret` (`GOCSPX-...`) **kaynak koda gömülü** durumda. Bu dosya `.gitignore` kapsamında değil.

Bunlara ek olarak, geçmiş konuşma dosyasında (`transcript.jsonl`) **bu anahtarların hepsi düz metin olarak** yer alıyor — yani sızma yüzeyi `.env` ile sınırlı değil.

**Yapılacak:**
1. Cloudflare API Token'ı **iptal et**, yeni token üret — yetkiyi yalnızca `D1:Edit` + `Workers R2 Storage:Edit` ile sınırla.
2. R2 Access/Secret Key çiftini **rotasyona sok**.
3. 9 LLM anahtarının tamamını **iptal edip yenile**.
4. Google OAuth Client Secret'ı **yenile**; `firebase_config.py`'den çıkarıp `.env`'e taşı.
5. `.gitignore`'a `.env`, `src/ui/firebase_config.py`, `data/tsistem.db`, `data/.remembered_user.json` ekle.
6. Repo geçmişinde `.env` commitlenmişse `git filter-repo` ile temizle.

### 1.2 Kimlik doğrulama bypass'ı (KRİTİK)

`src/ui/views/auth_view.py:74-93`:

```python
g_email = query_params.get("google_email") or query_params.get("google_login_email")
if g_email:
    user, is_complete, missing = auth_service.handle_google_auth({"email": g_email, ...})
    if is_complete:
        st.session_state.authenticated = True
        st.session_state.user = user
```

Hiçbir token, imza veya kod doğrulaması yok. `check_mandatory_fields_complete` (auth_service.py:286-290) admin/hakem için koşulsuz `(True, [])` döndürüyor.

> **`http://localhost:8501/?google_email=admin@tsistem.org` adresini açan herkes şifresiz tam ADMIN oturumu açar.**

Bilinmeyen bir e-posta girildiğinde ise `handle_google_auth` (auth_service.py:316-333) otomatik yeni `yarismaci` hesabı oluşturur → sınırsız hesap üretimi.

**Yapılacak:** Bu blok tamamen kaldırılacak; Google girişi yalnızca `exchange_google_code()` (satır 156-186) üzerinden, `state` parametresi CSRF doğrulamasıyla ve ID token `iss`/`aud`/`exp` kontrolüyle yapılacak.

### 1.3 FastAPI RBAC'ı kozmetik (KRİTİK)

`src/security/auth.py:26-28`:

```python
x_user_role: Optional[str] = Header("ADMIN", alias="X-User-Role"),
x_user_id:   Optional[str] = Header("usr_default", alias="X-User-Id"),
```

Token yok, oturum yok, DB doğrulaması yok, **varsayılan değer `"ADMIN"`**. Yani:

```bash
curl http://localhost:8000/api/admin/calibration   # header bile göndermeden ADMIN
```

`main.py:66-68` CORS varsayılanı `"*"` olduğu için tarayıcıdan da erişilebilir.

**Yapılacak:** JWT (HS256, kısa ömürlü) tabanlı gerçek oturum; `require_roles` bu token'ın claim'lerini okuyacak; header varsayılanları kaldırılacak.

### 1.4 Zayıf şifre hash'i (YÜKSEK)

`auth_service.py:31-33` → `hashlib.sha256(password)` — **salt yok, key stretching yok**. Ayrıca seed hesaplar `admin@tsistem.org / admin123` ve `hakem@tsistem.org / hakem123` her uygulama açılışında hem yerel SQLite'a hem **canlı D1'e** `INSERT OR REPLACE` ile yazılıyor (satır 122-151). Yani prod'da şifreyi değiştirseniz bile bir sonraki açılışta geri dönebilir.

**Yapılacak:** `argon2-cffi` veya `bcrypt`; seed hesaplar yalnızca `TSISTEM_BOOTSTRAP=1` ortam değişkeni varken ve şifre `.env`'den okunarak oluşturulacak.

---

## 2. MEVCUT DURUM HARİTASI

### 2.1 Katman mimarisi (gerçekte olan)

```
                    ┌──────────────────────────────────┐
                    │  Streamlit UI (src/ui/)          │
                    │  app.py 51KB · 15 modül          │
                    └───────┬──────────────┬───────────┘
                            │              │
              ┌─────────────┘              └──────────────┐
              │ YOL A (HTTP)                 YOL B (doğrudan)
              ▼                                           ▼
    ┌────────────────────┐                    ┌───────────────────────┐
    │ api_client.py      │                    │ database/db.py 76KB   │
    │ dashboard, hakem,  │                    │ yonetici, yarismaci,  │
    │ karsilastirma      │                    │ auth_service          │
    └─────────┬──────────┘                    └───────────┬───────────┘
              ▼                                           │
    ┌────────────────────┐                                │
    │ FastAPI            │                                │
    │ main.py + routes   │                                │
    │ + ui_adapter.py    │──────────────┐                 │
    └────────────────────┘              │                 │
                                        ▼                 ▼
                             ┌──────────────────┐  ┌──────────────┐
                             │ mock_data.py     │  │ SQLite       │
                             │ (DB boşsa!)      │  │ tsistem.db   │
                             └──────────────────┘  └──────┬───────┘
                                                          │
                                                    ┌─────▼──────┐
                                                    │ D1 (REST)  │
                                                    │ + R2       │
                                                    └────────────┘
```

**Bu şemadaki üç yapısal kusur:**

1. **İki paralel veri yolu var.** `yonetici.py` ve `yarismaci.py` FastAPI'yi tamamen atlayıp doğrudan `db.py`'ye gidiyor; `hakem.py` ve `dashboard.py` ise `api_client` → FastAPI → `ui_adapter` → `db.py` yolunu kullanıyor. İki yol farklı kolon adları, farklı status değerleri ve farklı `referee_id`'ler yazıyor.
2. **`ui_adapter.py` DB boşsa `mock_data`'ya düşüyor** (satır 43-55, 493, 581, 646). "Canlı" backend bile sahte veri döndürüyor — kullanıcının *"demo veri istemiyorum"* şikâyetinin doğrudan kaynağı.
3. **`db.py` içinde iki farklı kalıcılık felsefesi** yaşıyor: satır 1-1340 arası "SQLite birincil + D1 yedek", satır 1341-1772 arası "D1 birincil + SQLite yedek". İkisi farklı şemalar varsayıyor.

### 2.2 Modül envanteri ve durum notu

| Modül | Boyut | Durum |
|---|---|---|
| `src/ui/app.py` | 51 KB | Ana kabuk + navbar + takımlar + şartnameler + profil. Kendi CSS'ini enjekte ediyor. |
| `src/ui/views/hakem.py` | 74 KB | 5 adımlı değerlendirme istasyonu. En olgun ekran. |
| `src/ui/views/auth_view.py` | 37 KB | Giriş/kayıt. **4 ayrı `<style>` bloğu** enjekte ediyor. Bypass açığı burada. |
| `src/ui/sartname_rehber.py` | 34 KB | Dosya sistemi kataloğu + hardcoded fallback'ler. |
| `src/ui/auth_service.py` | 33 KB | D1 + SQLite çift yazım. Tek düzgün çalışan D1 tablosu (`auth_users`). |
| `src/ui/pdf_gorunum.py` | 32 KB | PyMuPDF önizleme. Zoom/kaydırma eksik. |
| `src/ui/views/yonetici.py` | 31 KB | Admin CRUD. UI tam, kalıcılık **sıfır**. |
| `src/ui/views/yarismaci.py` | 23 KB | Vitrin + rapor yükleme + karne. Karne bloğu erişilemez. |
| `src/ui/mock_data.py` | 23 KB | **Sahte veri üreteci.** Hâlâ aktif olarak hakem/dashboard'a besleniyor. |
| `src/ui/docx_gorunum.py` | 21 KB | DOCX önizleme. Office Online viewer URL'i çalışmıyor. |
| `src/database/db.py` | 76 KB | İki uyumsuz şema, 30+ yutulmuş hata, 1 çift tanımlı metot. |
| `src/evaluation/evaluator.py` | 32 KB | Gerçek 3 katmanlı AI motoru + heuristik simülasyon fallback. |
| `src/api/routes.py` | 29 KB | Gerçek boru hattı (güvenlik → PDF → kontroller → AI → DB). UI'dan kullanılmıyor. |
| `src/api/ui_adapter.py` | 29 KB | Streamlit adaptörü. Mock'a düşüyor. |
| `src/ai/spec_analyzer.py` | 5 KB | **LLM yok** — regex + sabit metin. |
| `src/ai/template_analyzer.py` | 9 KB | **LLM yok** — regex + hardcoded rubrik. |
| `src/services/doc_converter.py` | 2 KB | **Linux'ta hep `None`** — Windows COM / docx2pdf. |
| `src/services/r2_service.py` | 5 KB | Upload çalışıyor; download/presigned hiç çağrılmıyor. |

### 2.3 Ölü dosyalar (hiçbir yerden import edilmiyor — 435 satır)

- `src/ui/demo.py` (113 satır)
- `src/ui/views/yarismaci_paneli.py` (79 satır — %100 hardcoded karne)
- `src/ui/views/hakem_paneli.py` (142 satır — %100 sahte metrik)
- `src/ui/views/yonetici_paneli.py` (101 satır — "142 başvuru, 118 değerlendirilen, 74.8 ortalama")

---

## 3. NE YAPILMIŞ (gerçekten çalışan kısımlar)

Bu bölüm, üstüne inşa edilebilecek sağlam temeli listeler. Sıfırdan yazılması gereken bir sistem değil.

### ✅ Sağlam ve korunması gereken

| Bileşen | Konum | Neden sağlam |
|---|---|---|
| **Kullanıcı yönetimi** | `admin_kullanicilar.py` + `auth_service.py` | Şema ile sorgular uyumlu; D1 + SQLite çift yazım gerçekten çalışıyor. Rol atama, durum, şifre sıfırlama, silme, ana admin koruması hepsi işliyor. **Projenin tek uçtan uca çalışan CRUD'u.** |
| **3 katmanlı AI değerlendirme** | `evaluation/evaluator.py:343-372` | Analyst (LLM) → Fact-Checker (Python n-gram doğrulaması, satır 295-340) → Synthesizer (Pydantic + kalibrasyon). **Katman 2 gerçek bir halüsinasyon filtresi** — rapor metninde bulunmayan alıntıyı siliyor. Kullanıcının #179'da istediği "çok katmanlı, birbirinden haberdar" mimari fiilen kurulmuş. |
| **Prompt injection + KVKK koruması** | `security/guard.py` | 6 regex kalıbı + **Türkçe→ASCII normalizasyonu ile ikinci tarama** (satır 23-38). Sadece bayrak koymuyor, ifadeyi `[ŞÜPHELİ TALİMAT KALDIRILDI]` ile değiştiriyor. TCKN/telefon/e-posta maskeleme. PDF magic bytes + 30 MB sınırı. **Projedeki en iyi yazılmış modül.** |
| **Benzerlik algoritması** | `similarity/vector_store.py` | Harici bağımlılık yok; `difflib.SequenceMatcher` ile bütünsel + cümle-zirvesi harmanı, HIGH ≥0.70 / MEDIUM ≥0.40 eşikleri. Kaba ama gerçek bir ölçüm. |
| **FastAPI boru hattı** | `api/routes.py:126-219` | Yükleme → güvenlik taraması → PDF metin → KVKK maskeleme → R2/disk → 5 MVP kontrolü → AI → DB. Doğru sıralanmış tam bir akış. |
| **R2 yükleme** | `services/r2_service.py:55-92` | boto3, `signature_version="s3v4"` + `addressing_style="path"` — R2 için doğru kombinasyon. |
| **PDF önizleme motoru** | `pdf_gorunum.py` + `hakem.py:588-683` | PyMuPDF ile gerçek sayfa render, kanıt vurgulama (`_kanit_goster`, hakem.py:181-293). |
| **Hakem 5 adımlı akış** | `views/hakem.py:296-1316` | Kullanıcının tarif ettiği yapı (künye → PDF → şartname denetimi → rubrik puanlama → mühürleme) birebir kurulmuş. |
| **Rubrik çözümleme zinciri** | `evaluation/rubric.py:170-222` | DB'de tanım varsa AI ona uyuyor, kendi kriter uydurmuyor. Kullanıcının #253'teki *"YENİ KRİTER OLUŞTURMAMALI"* kuralı doğru kodlanmış. |
| **Veri seti analizi** | `data/competition_migration_plans.json` | 60 yarışma için şartname/aşama/seviye envanteri ve taşıma stratejisi çıkarılmış — **çok değerli, hazır girdi**. |

### 🟡 Yapılmış ama bağlanmamış (kod var, UI'a bağlı değil)

| Özellik | Konum | Durum |
|---|---|---|
| Yarışmacı geri bildirim/karne API'si | `routes.py:385-441`, `feedback/generator.py` | Tam çalışan `strengths`, `areas_to_improve`, `actionable_roadmap`, `pedagogical_advice` + PDF üretimi. **Streamlit hiç çağırmıyor.** |
| Hakem chat asistanı | `evaluation/chat_assistant.py`, `routes.py:364` | Rapor bağlamlı soru-cevap. **Hakem panelinde sohbet kutusu yok.** |
| Kalibrasyon yönetimi | `routes.py:658-729` | İntihal eşiği, AI offset/slope, hakem uyarı farkı. **Admin UI'da yok.** |
| Otomatik hakem dağıtımı | `db.py:381-413` `auto_distribute_reports` | Yazılmış, **hiçbir butona bağlı değil**. |
| Doğru atama metodu | `db.py:368-379` `assign_referee_to_report` | `reports.referee_id`'yi güncelleyen doğru sürüm. Admin paneli **yanlış olanı** çağırıyor. |
| Doğru CRUD metotları | `db.py:415-566` `save_competition`, `save_stage` | Şemayla **tam uyumlu**. Admin paneli bunları değil, uyumsuz `upsert_*` sürümlerini kullanıyor. |
| Karne PDF üreteci | `ui/karne_pdf.py:101` | Çalışan üreteç. `hakem.py:1306` **yanlış imzayla** çağırıyor (3 argüman vs 2) → `TypeError` → `except: pass` → buton hiç görünmüyor. |
| LLM tabanlı rubrik çıkarıcı | `rubric_extractor.py:200-249` `_llm_extract` | 50 satır Claude + OpenAI kodu. **Hiçbir yerden çağrılmıyor** — `extract_rubric_from_text` doğrudan heuristik'e gidiyor. |

> **Bu tablo planın en önemli çıkarımıdır:** eksik özelliklerin çoğu "yazılmamış" değil, **"yazılmış ama bağlanmamış"**. Faz planında bunlar en yüksek getirili işler olarak öne alınmıştır.

---

## 4. NE YAPILMAMIŞ / KIRIK

### 4.1 🔴 VERİ KATMANI — en kritik blok

#### 4.1.1 D1'de şema yok

Projede `wrangler.toml`, `.sql` migration dosyası, `migrations/` dizini **yok**. D1'de tablolar yalnızca kazara oluşuyor:

| Tablo | D1'de nasıl oluşuyor | Sonuç |
|---|---|---|
| `auth_users` | `auth_service._init_db()` her açılışta `CREATE TABLE IF NOT EXISTS` gönderiyor | ✅ Doğru |
| `reports` | `_sync_to_cloudflare_d1` (db.py:629-639) **7 kolonluk kırpılmış** sürüm yaratıyor | ❌ `r2_url`, `decision`, `stage_code`, `page_count`, `app_id` yok |
| `competition_rubrics` | `_sync_rubric_to_cloudflare_d1` (db.py:969-980) **eski şemayla** yaratıyor | ❌ Admin panelinin yazdığı şemayla uyumsuz |
| Diğer 10 tablo | — | ❌ **Hiç yaratılmıyor** |

Dahası, `_sync_to_cloudflare_d1`'deki 7 kolonlu `CREATE TABLE IF NOT EXISTS reports` **aktif zarar veriyor**: `IF NOT EXISTS` olduğu için doğru şemanın sonradan yaratılmasını engelliyor.

#### 4.1.2 Aynı tablo adına iki uyumsuz şema

| Tablo | Yerel `_init_sqlite()` şeması | `execute_d1` bloğunun varsaydığı şema | Sonuç |
|---|---|---|---|
| `competitions` | `domain`, `sub_category` (NOT NULL), `logo_slug`, `sartname_pdf_path`, `UNIQUE(name, sub_category)` | `levels`, `logo_url`, `sartname_url`, `ON CONFLICT(slug)` | `upsert_competition` **3 ayrı hatayla** patlar: kolon yok + NOT NULL ihlali + `ON CONFLICT` hedefi yok |
| `competition_stages` | `sablon_file_path` | `sablon_docx_url`, `sablon_pdf_url` | Aşama ekleme **hiç çalışmıyor** |
| `competition_rubrics` | `category_id` PK, `criteria_json` | `rubric_id`, `competition_id`, `stage_code`, `criterion_code`, `max_score` | Rubrik kaydı **hiç çalışmıyor**; ayrıca `delete_competition` bu tablo üzerinde tehlikeli DELETE çalıştırıyor |
| `reports` | `filename`, `project_name`, `category` (hepsi NOT NULL) | `app_id`, `file_name`, `page_count` | Yarışmacı rapor yüklemesi **hiç kaydedilmiyor** |
| `auth_users` | `name` (surname yok) | `SELECT email, name, surname` (yonetici.py:544) | **Hakem havuzu her zaman boş** |

#### 4.1.3 Hiç yaratılmayan ama kullanılan 3 tablo

| Tablo | Kullanan | Sonuç |
|---|---|---|
| `competition_requirements` | `db.py:1462, 1549, 1562, 1575` · `yonetici.py:306, 312, 348, 371` | Şartnameden çıkarılan kurallar **kaybolur** → "Onaylanan Kurallar (0 Adet)" |
| `report_assignments` | `db.py:1667, 1689` · `yarismaci.py:324` | **Hakem ataması kaydedilmez**; ayrıca `score`/`eval_json` kolonları okunuyor ama hiç yazılmıyor |
| `applications` | `db.py:1714, 1732, 1755` · `yarismaci.py:229` | **Başvuru hiç oluşmaz**; `create_application` çağrılmıyor bile |

#### 4.1.4 Sessiz başarısızlık deseni (sistemik)

`db.py` içinde **13 ayrı yerde** aynı desen var:

```python
try:
    self.execute_d1(sql, params)
    conn = sqlite3.connect(DB_FILE)
    cursor.execute(sql, params)        # <- burada patlar
    conn.commit()
except Exception:
    pass                               # <- hata yutulur
return True                            # <- HER ZAMAN başarı
```

Satırlar: `1454, 1473, 1526, 1543, 1570, 1600, 1627, 1657, 1680, 1703, 1725, 1748, 1770`.
Ayrıca `execute_d1:1377`, `sartname_rehber.py`'de 9 yer, `yarismaci.py`'de 4 yer, `doc_converter.py`'de 2 yer, `evaluator.py`'de 4 yer.

**Bu desen, projedeki hataların %70'ini görünmez kılan tek etkendir.**

#### 4.1.5 `execute_d1`'in davranış kusurları (`db.py:1341-1379`)

1. Kimlik bilgisi yoksa satır 1343-1344 **erken `return []`** yapıyor → `except` bloğuna hiç girilmiyor → yerel SQLite fallback'i **hiç çalışmıyor**.
2. HTTP 200 + `success: false` (kısmi D1 hatası) durumunda `except` tetiklenmiyor → sessizce `[]` dönüyor.
3. INSERT/DELETE'te D1 `results: []` döndürdüğü için çağıranlar "boş = hata" varsayıp gereksiz yere SQLite'a düşüyor.
4. Hata **hiç loglanmıyor** (`except Exception as e:` ama `e` kullanılmıyor).

#### 4.1.6 Üç kopya D1 istemcisi

| Konum | Dönüş tipi | Timeout | Loglama |
|---|---|---|---|
| `db.py:658` `_d1_query` | `bool` | 10 sn | ✅ var |
| `db.py:1341` `execute_d1` | `List[Dict]` | 15 sn | ❌ yok |
| `auth_service.py:43` `_query_d1` | `Optional[List]` | 5 sn | kısmi |

Üçü de `urllib.request` kullanıyor — retry yok, connection pooling yok. Streamlit her rerun'da yeni TCP bağlantısı açıyor.

#### 4.1.7 Enum kaosu

**`status` — dört ayrı kelime dağarcığı:**

| Değer ailesi | Üreten | Okuyan |
|---|---|---|
| `READY_FOR_REFEREE` | `db.py:373, 402, 599, 650`; `routes.py:200, 274` | `hakem.py:742, 793` |
| `COMPLETED` / `PENDING` / `EVALUATION_COMPLETED` | `db.py:790, 1078`; `ui_adapter.py:105, 324, 675` | `ui_adapter.py:105` |
| `Beklemede` / `Hakeme Atandı` / `Değerlendirildi` | `yarismaci.py:200, 366`; `db.py:1670` | `yarismaci.py:316-320`; `yonetici.py:557` |
| `tamamlandi` | `hakem.py:1296` | **hiçbir yerde okunmuyor** |

Somut sonuç: hakem raporu mühürlediğinde status `"tamamlandi"` oluyor; yarışmacı ekranı `"Değerlendirildi"` bekliyor (`yarismaci.py:319`) ve `else` dalı olmadığı için **hiçbir rozet göstermiyor**. Hakem paneli ise `READY_FOR_REFEREE` arıyor → Türkçe status'lu raporları **hiç göremiyor**.

**`decision` — kod/şema çelişkisi:**
- Şema yorumu (`db.py:246`) ve `schemas.py:125`: `APPROVED / REJECTED / NEEDS_REVISION`
- `db.save_referee_decision` (db.py:1076): **sabit `"APPROVED"`** — hakem ne derse desin
- `hakem.py:1295`: `"ONAYLANDI"` (Türkçe)

#### 4.1.8 Çift yazım çakışması

`hakem.py:1290-1301` mühürleme butonu **iki kez yazıyor**:

```python
db.update_referee_decision(referee_id=referee_id, decision="ONAYLANDI", status="tamamlandi")  # 1. yazım
sonuc = api_client.hakem_karari_gonder(...)   # 2. yazım — dönüş bile kullanılmıyor
```

İkinci çağrı `ui_adapter.py:661-683` üzerinden `db.save_referee_decision(referee_id="HAKEM-EMRE-1")` çalıştırıyor → **gerçek hakem kimliği saniyeler içinde hardcoded bir string ile eziliyor.**

Ayrıca **kriter bazlı hakem puanları hiçbir yere kaydedilmiyor** — sadece toplam float. İtiraz/denetim izi yok.

#### 4.1.9 `hash()` ile kimlik üretimi

`yarismaci.py:182, 197, 363` · `app.py:638` · `db.py:1711`:

```python
app_id = f"APP-{abs(hash(secili_takim + secili_yarisma)) % 90000 + 10000}"
```

Python'da string `hash()` **PYTHONHASHSEED ile süreç başına randomize**. Uygulama yeniden başladığında aynı takım adı **farklı kod** üretir. Ayrıca `% 90000` ile doğum günü paradoksu: ~350 raporda %50 çakışma. `uuid.uuid4()` aynı dosyada zaten kullanılıyor (db.py:279, 431, 517).

#### 4.1.10 Çift tanımlı metot

`db.py:1002` ve `db.py:1271` → `get_rubric_by_category` **iki kez tanımlı**. Python son tanımı tutar → satır 1002-1046'daki 4 aşamalı çözümleme (tam ad → GENEL → herhangi aşama → LIKE) **tamamen ölü kod**.

---

### 4.2 🔴 ROL BAZLI EKRAN DENETİMİ

#### 4.2.1 YARIŞMACI (Üye)

**Görebildiği ekranlar:** Ana Sayfa · Başvurularım & Karne (3 alt sekme) · Takımlarım · Şartnameler · Profilim

| Ekran / Bileşen | Veri kaynağı | Gerçek mi? |
|---|---|---|
| Ana sayfa 4 modül kartı | i18n sabitleri | Statik (2 kart aynı yere gidiyor — app.py:372, 386) |
| **Ana sayfa takvim panosu** | `app.py:419-442` | ❌ **%100 hardcoded HTML** ("15 Nisan 2026", "15 Haziran 2026", "02-06 Eylül 2026") |
| Vitrin — yarışma listesi | `db.list_all_competitions()` | ✅ DB — ama tablo **boş** |
| Vitrin — alan/seviye filtre seçenekleri | `yarismaci.py:64, 66` | ⚠️ Hardcoded (`yonetici.py:34-50`'den kopyalanmış) |
| **Vitrin — seviye filtresi** | `yarismaci.py:79` `y_seviye not in c_lev` | ❌ **BOZUK** — yerel `competitions`'ta `levels` kolonu yok → `c_lev=""` → seçim yapılırsa **liste tamamen boşalır** |
| Vitrin — "Son Başvuru" | `schedule_json` yoksa | ⚠️ `"28.02.2026"` hardcoded. **Kalan gün / geri sayım yok.** |
| Vitrin — logo | `sartname_rehber` → R2 | ❌ R2 dalı bozuk (§4.5.1) → her kartta "TF" placeholder |
| Vitrin — "Rapor Yükle" butonu | `yarismaci.py:126-128` | ❌ Sadece session değişkeni set ediyor. **Streamlit'te `st.tabs()` programatik seçilemez** → kullanıcı aynı sekmede kalır, hiçbir mesaj görmez |
| Takım listesi | `data/takimlar.json` | ❌ **Yerel JSON** — DB'de `teams` tablosu yok |
| **Takım üyeleri** | `app.py:704-710` | ❌ **Sabit uydurma isimler**: "Ahmet Yılmaz (Üye)", "Prof. Dr. Mehmet (Danışman)" |
| Takıma katılma | `app.py:663-675` | ❌ **Girilen kod hiç doğrulanmıyor**; herhangi bir sayı "Katılınan Takım 999999" adıyla yerel kayıt açar; kaptanın haberi olmaz |
| Rapor yükleme | R2 + `reports` INSERT | ⚠️ R2 gerçek ama `success` **kontrol edilmiyor** → R2 kapalıyken hata metni `r2_url` olarak yazılıyor ve yine "başarıyla yüklendi" deniyor |
| **Başvurularım listesi** | `yarismaci.py:234` `SELECT * FROM reports` | 🔴 **WHERE yok** — sistemdeki **tüm yarışmacıların tüm raporları** çekiliyor → gizlilik ihlali |
| **Karne / puan** | `yarismaci.py:324-328` `report_assignments.score` | ❌ **Erişilemez kod.** Tablo yok; hakem puanı `reports.referee_score`'a yazılıyor. **Yarışmacı hiçbir koşulda puanını göremez.** |
| Rapor indirme | `yarismaci.py:382` | ❌ `st.button` (download_button değil), `if` yok → **tıklanınca hiçbir şey olmuyor** |
| KVKK rozeti | `app.py:1017-1022` | ❌ Hardcoded "✓ Onaylıdır / Aktif Üye" |
| Profil | `auth_service` | ✅ Gerçek DB yazma |

**Çökme riski:** `yarismaci.py:280` → `r.get("stage_code").upper()`. `stage_code` NULL olabilir (`db.save_report` bu kolonu hiç yazmıyor) → `AttributeError` → **tüm Başvurularım sekmesi çöker.**

**Yarışmacı için hiç yapılmamış olanlar:**
- Gerçek "yarışmaya başvur" akışı (`db.create_application` yazılmış, **hiç çağrılmıyor**)
- Uygunluk kontrolü (takım büyüklüğü, danışman şartı, eğitim seviyesi — `category_requirements`'ta veri var, okunmuyor)
- Deadline kontrolü — süresi geçmiş aşamaya rapor yüklenebiliyor
- Mükerrer yükleme engeli
- Revizyon akışı (`decision = NEEDS_REVISION` şemada var)
- Karne PDF indirme (`karne_pdf` import edilmiş, kullanılmamış — `yarismaci.py:27`)
- Kriter bazlı puan kırılımı, radar grafiği, güçlü yönler / gelişim önerileri
- Bildirim (e-posta / uygulama içi)
- **i18n: `views/yarismaci.py`'de `t()` çağrısı sayısı 0** — dil EN'e alındığında ekran Türkçe kalıyor

#### 4.2.2 HAKEM

**İzolasyon gerçekten uygulanmamış.** Dört bağımsız kanıt:

**Kanıt 1** — SQL filtresi kasıtlı olarak delinmiş (`db.py:758-760`):
```python
query += " AND (referee_id = ? OR referee_id LIKE ? OR referee_id IS NULL
              OR referee_id = '' OR referee_id = 'usr_hakem_ef6def'
              OR referee_id = 'hakem@tsistem.org')"
```
`referee_id IS NULL` → **atanmamış her rapor her hakeme görünür.** Hardcoded `usr_hakem_ef6def` üstelik gerçek seed hakem id'si (`usr_hakem_master`) bile değil.

**Kanıt 2** — API modunda `referee_id` hiç gönderilmiyor (`api_client.py:53-58`); `ui_adapter.py:544-611` hakem kavramını bilmiyor, kategorinin **tüm** raporlarını döndürüyor. `start.py:41` varsayılan başlatmada `T_SISTEM_API` set ettiği için **normal kullanımda izolasyon sıfır.**

**Kanıt 3** — Doğru izolasyon fonksiyonu `db.py:1684-1707` `list_assigned_reports_for_referee` **hiçbir yerden çağrılmıyor.**

**Kanıt 4** — Atama zinciri kopuk: `report_assignments` tablosu yok, `reports.referee_id` hiç güncellenmiyor, hata yutuluyor.

**Diğer hakem bulguları:**

| Bulgu | Konum | Detay |
|---|---|---|
| **AI çalışmadan sahte AI puanı** | `api_client.py:88-89` | Her rapor **önce `mock_data._rapor()` ile rastgele üretiliyor**, sonra sadece 5 alan DB'den üzerine yazılıyor. ADIM 5'teki "AI Ön Puanı" kutusu (`hakem.py:1212`) AI hiç çalıştırılmadan **rastgele mock puanları** gösteriyor |
| **Rubrik tablosu her kategoride yanlış** | `rubrik.py:71-75` | `getir()` eşleşme bulamazsa `YARISMALAR[0]` döndürüyor. Panele slug geliyor, sözlükte `hyz-otr-2026` var → **hangi kategori seçilirse seçilsin HYZ ÖTR'nin 9 kriteri** gösteriliyor |
| **İntihal kontrolü hiç çalışmıyor** | `hakem.py:722-728` | `run_all_checks` çağrısında `corpus` **geçilmiyor** → mağaza boş → `matches: []` → `hakem.py:936` **sabit %8** gösteriyor ve "İntihal Şüphesi Bulunmadı" diyor. FastAPI rotası (`routes.py:185`) korpusu doğru besliyor ama Streamlit onu kullanmıyor |
| Sabit takvim bandı | `hakem.py:557-577` | "20 Ağustos 2026", "Kalan: **23 Gün**", "16–22 Eylül" — hardcoded HTML |
| Şartname caption `None` basıyor | `hakem.py:884` | `kz_data` iki farklı anahtar seti ile gelebiliyor (İngilizce/Türkçe) → her durumda bazı alanlar `None` |
| Sayfa limiti hep 20 | `hakem.py:851-852` | Fallback `maksimum_sayfa_siniri` döndürüyor, kod `max_pages` arıyor |
| Şartname denetimi hep aynı 5 başlık | `runner.py:145-165` | Aynı anahtar uyuşmazlığı → kategori ne olursa olsun sabit başlık listesi |
| `weighted_total_score` hep `None` | `hakem.py:771-774` | Pydantic şemasında bu alan yok → düşüyor → kalibrasyon sonucu atılıyor → sıfır kriterde **84.0 uyduruluyor** |
| Karne PDF butonu hiç görünmüyor | `hakem.py:1306` | `uret(rapor, yarisma, not_metni)` — 3 argüman, fonksiyon 2 alıyor → `TypeError` → `except: pass` |
| Bozuk PDF'te uydurma metin | `hakem.py:711-713` | PDF okunamazsa AI'a `"TEKNOFEST 2026 ... Algoritma mimarisi, veri setleri, sonuçlar ve kaynakça."` tek cümlesi gidiyor ve **rapor bunun üzerinden puanlanıyor** |
| Hakem notu geri yüklenmiyor | `hakem.py:1236` | `referee_notes` anahtarı hiçbir veri yolunda üretilmiyor |
| Chat asistanı yok | — | `chat_assistant.py` yalnızca FastAPI'den erişilebilir; hakem panelinde sohbet kutusu **hiç yok** |
| i18n | `views/hakem.py` | 1316 satır, **`t()` çağrısı: 0** |

#### 4.2.3 YÖNETİCİ (Admin)

**Admin panelinin CRUD gerçeklik matrisi:**

| Modül | UI | İş mantığı | Kalıcılık | Durum |
|---|---|---|---|---|
| Yeni Yarışma Oluştur | ✅ | ✅ | ❌ Şema uyuşmazlığı | **Kırık** |
| Yarışma listeleme/arama/filtre | ✅ | ✅ | ⚠️ Tablo boş | Çalışır ama boş |
| Yarışma düzenleme | ✅ | ⚠️ | ❌ | **Kırık** |
| Bağımsız takvim | ✅ | ⚠️ `text_input`, doğrulama yok | ❌ | Yarım — ayrıca `sonuc_tarihi` **her güncellemede siliniyor** |
| Şartname → R2 yükleme | ✅ | ✅ Gerçek boto3 | ⚠️ `success` kontrolsüz | Kısmen |
| **AI Kural Çıkarıcı** | ✅ | ❌ **LLM yok** — regex + 4 sabit kural | ❌ Tablo yok | **Sahte AI** |
| Canlı kural tablosu | ✅ | ❌ `selectbox(index=0)` sabit → **her kayıtta rule_type sıfırlanıyor** | ❌ | **Bozuk** |
| Aşama ekleme | ✅ | ✅ | ❌ Kolon yok | **Kırık** |
| Şablon → R2 | ✅ | ✅ | ⚠️ Kontrolsüz | Kısmen |
| **Word → PDF** | ✅ | ❌ **Windows-only** | — | **Kırık** — üstelik "başarıyla dönüştürüldü" mesajı basıyor |
| **AI Rubrik Çıkarıcı** | ✅ | ❌ **LLM yok** — 3<başlık ise hardcoded rubrik | ❌ Tablo çakışması | **Sahte AI** |
| Rubrik editörü | ✅ | ⚠️ Toplam puan **silinenleri de sayıyor** | ❌ | Erişilemiyor |
| **Hakem havuzu** | ✅ | ❌ `SELECT ... surname` → kolon yok | ❌ | **Her zaman boş** |
| **Rapor havuzu** | ✅ | ❌ `file_name` vs `filename` | ❌ | **Her zaman boş** |
| **Rapor yönlendirme** | ✅ | ❌ `report_assignments` tablosu yok | ❌ | **Kırık** ("başarıyla atandı" der) |
| Yarışmayı sil | ✅ | ✅ | ⚠️ Kısmen | Kısmen — R2 dosyaları yetim kalır |
| **Kullanıcı yönetimi** | ✅ | ✅ | ✅ | **ÇALIŞIYOR** |

**Admin yetkilendirme sorunları:**
- `app.py:316` ve `app.py:485` admin menüsünü **`else:` dalında** çiziyor → `yarismaci`/`uye`/`hakem` **dışındaki her rol** (`yonetici`, boş string, tanımsız rol) admin paneline düşüyor
- `admin_kullanicilar.py:125` `yonetici` rolü atanabiliyor ama `app.py`'de bu rol için dal yok → tutarsızlık
- `yonetici.py` ve `admin_kullanicilar.py`'de **modül içi rol kontrolü yok**
- Ana admin'in **rolü düşürülebiliyor / pasife alınabiliyor** (sadece silme korumalı, `admin_kullanicilar.py:165`) → sistemde admin kalmayabilir

**Admin için hiç yapılmamış olanlar:** çoklu hakem ataması · atama geri alma / yeniden atama · uzmanlığa göre eşleştirme (`users.specialty` var, kullanılmıyor) · sonuç ilanı / sıralama / ödül (`awards_json` var, UI yok) · denetim izi (audit log) · yarışma durumu (taslak/yayında/kapalı) · toplu rapor içe aktarma (`upload_raporlar_ui` **stub**) · e-posta bildirimi · yarışma logosu yükleme formu · Excel/CSV dışa aktarma · sayfalama · silme onayı · aşama **düzenleme** (sadece ekle/sil var) · **"Kaydet" butonu ile toplu kayıt** (kullanıcının #276'daki isteği)

---

### 4.3 🟠 TEMA — "giriş ekranı teması genel tema olmalı"

Bu, kullanıcının en çok tekrarladığı isteklerden biri (#231: *"uygulama genelinde giriş yap kayıt ol kısmındaki renk paletine uygun olarak temayı yeniden düzenle"*). Kök neden tek satırdır:

#### 4.3.1 `theme.py` fiilen ölü kod

```python
# theme.py:402
def inject_css(st): st.markdown(CSS, unsafe_allow_html=True)
```

**Tüm repoda tek eşleşme tanım satırı — hiçbir yerden çağrılmıyor.** Aynı şekilde `register_plotly_template()` (satır 57-71) de çağrılmıyor.

Sonuç: `theme.py:74-399` arasındaki **~325 satırlık CSS tasarım sistemi tarayıcıya hiç ulaşmıyor.** Uygulamanın gerçekte gördüğü CSS `app.py:136-233` + `auth_view.py`'deki 4 ayrı `<style>` bloğudur.

Bunun yüzünden uygulanmayanlar:
- Streamlit üst toolbar / deploy butonu gizleme (`theme.py:77-84`) → **kullanıcının #34 ve #275'te iki kez şikâyet ettiği şerit** hâlâ görünüyor
- 16.5px taban font (`theme.py:96`) → kullanıcının #246'daki *"genel uygulama fontu büyük olsun"* isteği karşılanmıyor
- `block-container` padding sıfırlama, `max-width:1400px`
- **Turuncu primary buton kuralı** (`theme.py:194-224`) → ana uygulamadaki tüm `type="primary"` butonlar **Streamlit varsayılan kırmızısında (`#FF4B4B`)**
- Segmented pill sekme tasarımı (`theme.py:300-338`) → `st.tabs` varsayılan alt-çizgi görünümünde
- Sayfa zemini `#F4F6F9` → hiçbir ekranda uygulanmıyor

Ayrıca repo kökünde **`.streamlit/config.toml` dosyası yok** → `primaryColor` hiç tanımlı değil.

#### 4.3.2 Auth ekranı ↔ ana kabuk görsel farkları

| Boyut | Giriş/Kayıt | Ana kabuk |
|---|---|---|
| **Primary buton** | Turuncu gradient `#F04823→#E03E1B` (**yalnız login formunda**) | **Streamlit kırmızısı `#FF4B4B`** |
| **Sekme dili** | Sahte pill (2 `st.button` + CSS) | Gerçek `st.tabs` — varsayılan alt-çizgi |
| **Input dolgusu** | `#F1F5F9` + `1.5px` kenar + inset gölge | **Stilsiz** — Streamlit varsayılanı |
| Kart konteyner | `st.container(border=True)` | `.t3-content-card` (12px radius) |
| Buton radius | 8px | Streamlit 0.5rem / navbar 8px |
| Logo boyutu | `use_container_width=True` (kolon genişliği) | Sabit 38×38px |
| Başlık ağırlığı | 850 / 800 | 900 / 800 |
| Ayırıcı rengi | `#E2E8F0` | `#F1F5F9` ve `#E2E8F0` karışık |

**En görünür kusur:** `auth_view.py`'de submit butonu turuncu yapan CSS (satır 295-311) **yalnızca `_render_login_form` içinde** enjekte ediliyor. `_render_register_form` (satır 590), `_render_forgot_password_form` (427, 472) ve `_render_google_complete_profile_view` (701) bu CSS'i görmüyor →

> **"Giriş Yap" sekmesinde buton turuncu, "Kayıt Ol" sekmesine tıklandığında aynı ekranda buton Streamlit kırmızısına dönüyor.**

#### 4.3.3 Diğer tema borçları

- **4 bağımsız CSS otoritesi:** `app.py:136`, `auth_view.py` ×4, `hakem.py:317`, `pdf_gorunum.py`, `docx_gorunum.py` — artı ölü `theme.py`
- **`app.py` ile `theme.py` aynı sınıf adlarını farklı değerlerle tanımlıyor:** `.t3-module-card` radius 14 vs 16px, gradient `#D9381E` vs `#D93815`, `.t3-badge-aktif` pastel vs dolu, `.t3-content-card` gölge neredeyse görünmez vs belirgin
- **`components.py`'nin ürettiği 12 CSS sınıfı hiçbir yerde tanımlı değil** (`ts-tile`, `ts-pill`, `ts-dot`, `ts-track`, `ts-fill`, `ts-card`, `ts-sub`, `ts-muted`, `ts-kv`, `ts-quote`…) → `stat_tile()`, `durum_pill()`, `puan_cubugu()` fonksiyonları **stilsiz** render oluyor; puan çubuğu hiç çizilmiyor. Bunlar `dashboard.py`, `hakem.py`, `karsilastirma.py`'de aktif kullanılıyor
- **137 hardcoded hex kodu:** `app.py` 59, `auth_view.py` 78. Büyük/küçük harf tutarsızlığı (`#94a3b8` vs `#94A3B8`)
- **~25 palet dışı ton:** `#FFDE59`, `#D9381E`, `#475569`, `#FED7AA`, `#FDBA74`, `#2563EB`, `#d03b3b`…
- **İki çakışan renk token seti:** yeşil `#16A34A` vs `#198754`, kırmızı `#DC2626` vs `#DC3545`, lacivert `#0F172A` vs `#1E293B`
- **Radius ölçeği:** 6, 8, 9, 12, 14, 16 — altı farklı değer, ölçek yok
- **Font-weight:** 750, 800, 850, 900 — standart dışı `750`/`850` değerleri
- **Dark mode yok, ama light-mode da zorlanmamış** → OS koyu temada `#1E293B` metinler koyu zeminde okunamaz hale geliyor
- **7× tekrarlanan inline `<hr>`**, 7× tekrarlanan bölüm başlığı stili, 3× tekrarlanan ortalanmış başlık bloğu (`auth_view.py`)
- **Ölü CSS:** `.t3-navbar` (theme.py:121) hiç kullanılmıyor; `.st-key-btn_text_forgot_pw` (auth_view.py:327-350, 24 satır) karşılık gelen buton hiç oluşturulmuyor; `GOOGLE_SVG_ICON` (auth_view.py:25) ölü sabit

#### 4.3.4 i18n

`i18n.py` **107 anahtar, TR/EN tam parite** — sözlük sağlam. Ama:

| Dosya | Satır | `t()` çağrısı |
|---|---|---|
| `app.py` | 1056 | 72 |
| `auth_view.py` | 731 | 24 |
| `views/hakem.py` | 1316 | **0** |
| `views/yonetici.py` | 575 | **0** |
| `views/yarismaci.py` | 382 | **0** |
| `views/dashboard.py` | 219 | **0** |
| `views/karsilastirma.py` | 203 | **0** |
| `views/admin_kullanicilar.py` | 216 | **0** |
| `components.py`, `charts.py` | 496 | **0** |

**~4.000 satırlık view katmanı %100 hardcoded Türkçe.** 13 i18n anahtarı tanımlı ama kullanılmıyor (`fullname_label`, `kvkk_text`, `btn_download_spec`, `forgot_password`…).

**Veri bütünlüğü hatası (i18n kaynaklı):** `app.py:976-1007`'de dil ternary'si seçenek **değerlerini** değiştiriyor:
```python
["ERKEK","KADIN"] if lang=="tr" else ["MALE","FEMALE"]
["Lisans","Önlisans",...] if lang=="tr" else ["Bachelor","Associate",...]
```
Bu değerler doğrudan DB'ye yazılıyor → **aynı alan iki farklı değer uzayına sahip oluyor.**

---

### 4.4 🔴 AI MOTORU

#### 4.4.1 Gerçek olan

`evaluator.py` üç sağlayıcılı zincir kuruyor:
1. **Anthropic** — `model="claude-sonnet-4-6"` (satır 214). ⚠️ **Bu geçerli bir Anthropic model ID'si değil** (gerçek format `claude-sonnet-4-5-20250929`) → her anahtarda 404 → `except: pass` (228) → katman sessizce atlanıyor
2. **Groq** — 4 model dener (satır 240). ⚠️ **`groq` paketi `requirements.txt`'de YOK** → `ImportError` → katman tamamen ölü
3. **OpenAI** — `gpt-4o-mini` (278). ⚠️ Yalnızca tekil `OPENAI_API_KEY` okunuyor; `.env`'deki `OPENAI_API_KEYS` (3 anahtar) **hiçbir yerde kullanılmıyor**

Yani **pratikte yalnızca 3. katman çalışıyor, o da tek anahtarla.**

Katman 2 (Fact-Checker, satır 295-340) gerçek bir kazanım: alıntının ilk `len/8/6/4` kelimelik n-gramını normalize edilmiş rapor metninde arıyor, bulamadığını siliyor. Kullanıcının *"kanıt yanlış yerleri işaretliyor"* şikâyetine doğru cevap.

#### 4.4.2 Heuristik simülasyon fallback — kullanıcı bunu fark etmiyor

Tüm LLM'ler başarısız olursa `_generate_smart_heuristic_evaluation()` (satır 429-554) devreye giriyor. **Puanlama tamamen sahte** (satır 501-504):

```python
oranlar = [0.85, 0.90, 0.88, 0.82, 0.86, 0.92]
secili_oran = oranlar[idx % len(oranlar)]
puan = round(cmax * secili_oran * 2) / 2
```

Rapor içeriğine **hiç bakmadan**, sadece kriterin sırasına göre %82-92 arası puan. **Boş bir rapor da mükemmel bir rapor da ~87/100 alır → "KABUL".**

Gerekçe ve eksikler de sabit şablon (satır 506-527). Tek "gerçek" kısım: rapordan seçilen bir cümlenin gerekçeye gömülmesi ve `quotes = secili_cumleler` — bunlar gerçek cümleler olduğu için **Katman 2 doğrulamasını da geçiyor**. Yani hakem sahte puanı gerçek alıntılarla desteklenmiş görüyor.

Üstüne `confidence_score: 0.92` **sabit** (satır 551) → ekranda "%92 güven" yazıyor.

**Bu, kullanıcının #291'deki *"HATASIZ BİR ŞEY İSTİYORUM"* isteğinin tam zıddıdır ve gizlidir.**

#### 4.4.3 `src/ai/` klasörü — "AI" değil

`spec_analyzer.py` ve `template_analyzer.py` **hiçbir LLM import etmiyor** (`anthropic`, `openai`, `groq` yok — sadece `os`, `json`, `re`, `pathlib`, `pymupdf`).

**`spec_analyzer.analyze_specification`:**
- Takım boyutu: tek regex (satır 48)
- Danışman şartı (satır 62): `... or "lise" in low_text` → **şartnamede "lise" kelimesi geçen her belgede danışman zorunlu sayılıyor**
- Kurallar (satır 81-118): **4 adet tamamen hardcoded metin**, her yarışma için birebir aynı
- "%15 intihal sınırı" (103): belgeden okunmuyor, koda gömülü
- Takvim (121-129): ilk bulunan 2 tarih körlemesine atanıyor; bulunamazsa `28.02.2026` / `15.09.2026 - 20.09.2026`

**`template_analyzer.analyze_template`:**
- Tek regex ile numaralı başlık (satır 55); puan bulunamazsa **her kritere 20.0**
- `if len(rubric_items) < 3:` (71) → **3'ten az başlık yakalanırsa tüm çıktı atılıyor** ve aşama koduna göre elle yazılmış 4-5 kriterlik sabit rubrik dönüyor (74-179)
- Gerçek TEKNOFEST şablonlarında bu regex nadiren 3+ eşleşme bulacağı için **pratikte neredeyse her zaman sabit rubrik dönüyor**

Bu, kullanıcının #205/#219/#220'deki *"rapor şablonu ile 4. adımdaki kriterler uyuşmuyor, kafasına göre değil ait olduğu aşamanın rapor şablonundaki puanlamaya göre yapılmalı"* şikâyetinin **kesin kök nedenidir.**

#### 4.4.4 `rubric_extractor.py`'nin LLM'i devre dışı

```python
# rubric_extractor.py:252-261
def extract_rubric_from_text(sartname_text, category_name, stage=None):
    return heuristic_extract(sartname_text, category_name, stage)
```

`_llm_extract()` (satır 200-249, 50 satır Claude + OpenAI kodu) **hiçbir yerden çağrılmıyor.** Ve `heuristic_extract` (122-171) docstring'inde açıkça yazıyor:

```python
"criteria": [],  # bilinçli boş -> normalize_rubric temiz varsayılana düşer
```

→ **Şartnameden çıkarılan rubrik HER ZAMAN 5'li sabit varsayılan kriter setidir.**

#### 4.4.5 `key_manager.py` sorunları

- Round-robin + failover doğru kurulmuş (`itertools.cycle`, thread-safe)
- ❌ **429 / rate-limit ayrımı yok**: `except Exception` her hatayı (401, 404, JSON parse) failover sebebi sayıyor → **model yanıtı bozuk diye 3 anahtar birden tüketiliyor**
- ❌ Backoff yok, anahtar sağlık takibi yok
- ❌ Sadece Anthropic'i yönetiyor; Groq ve OpenAI kendi ad-hoc `os.getenv().split(",")` mantıklarını kullanıyor
- ❌ Singleton `__new__` içinde init → anahtarlar süreç boyunca yenilenmiyor
- `self.index = 0` (satır 34) ölü alan

---

### 4.5 🟠 DOSYA / DOKÜMAN KATMANI

#### 4.5.1 Var olmayan metot çağrısı

```python
# sartname_rehber.py:51 ve :246
file_bytes = r2_service.download_file(r2_key)   # ← BÖYLE BİR METOT YOK
...
except Exception: pass
```

`R2Service`'in metotları: `slugify`, `upload_file`, **`download_bytes`**, `delete_file`, `generate_presigned_url`. `download_file` yok → her çağrı `AttributeError` → yutuluyor.

**Sonuç: R2'den logo ve şartname indirme hiç çalışmıyor, hiçbir log da yok.**

#### 4.5.2 Public URL üretimi yok

Üç farklı yaklaşım, üçü de kırık:

1. `r2_service.upload_file` **URL değil, ham object key döndürüyor** (satır 90) — bu key doğrudan DB'ye `r2_url` olarak yazılıyor
2. `storage.upload_file_bytes` (satır 48) **S3 API endpoint'ini** döndürüyor: `{endpoint_url}/{bucket}/{filename}` → `*.r2.cloudflarestorage.com` imzasız GET'i **401 ile reddeder**
3. `docx_gorunum.py:407` Office Online viewer'a bu adresi veriyor → Microsoft sunucusu çekemez → **viewer her zaman hata gösterir**

`.env`'de `CLOUDFLARE_R2_PUBLIC_URL` benzeri bir değişken **yok**. `generate_presigned_url` **hiçbir yerden çağrılmıyor**.

**Üç farklı bucket adı dolaşımda:** `t-sistem` (r2_service.py:25, .env), `t-sistem-raporlar` (storage.py:18), `t-sistem-raporlar.r2.cloudflarestorage.com` (docx_gorunum.py:407 hardcoded).

#### 4.5.3 Word → PDF Linux'ta çalışmıyor

`doc_converter.docx_to_pdf` (satır 14-67) iki yöntem dener:
1. `win32com.client` + `pythoncom` → **Windows + kurulu MS Word şart**
2. `docx2pdf` → yine Windows COM / macOS AppleScript; ayrıca **paket `requirements.txt`'de yok**

Docstring "LibreOffice destekli" diyor ama **kodda `soffice` çağrısı yok**. Linux'ta `return None`.

`yonetici.py:453` → `if pdf_path and pdf_path.exists():` → hep False → PDF üretilmez ama kullanıcıya **"başarıyla PDF'e dönüştürüldü!"** (satır 481) denir.

#### 4.5.4 PDF viewer eksikleri (kullanıcının #230 ve #245'te iki kez istediği)

- Zoom / oran değiştirme **yok**
- Serbest kaydırma **yok** — sayfa sayfa `number_input` navigasyonu var
- İki farklı görüntüleme seçeneği kafa karıştırıyor (#242)

#### 4.5.5 Bağımlılık borcu

**Kodda import ediliyor, `requirements.txt`'te YOK:**

| Paket | Kullanım | Kritiklik |
|---|---|---|
| `python-docx` (`import docx`) | 6 dosya | 🔴 Şablon analizi çöker |
| `groq` | evaluator, chat_assistant | 🔴 LLM zincirinin 2. halkası ölü |
| `Pillow` | logo işleme | 🟠 |
| `mammoth` | DOCX önizleme | 🟠 |
| `pypdf` + `PyPDF2` | ayrı ayrı 1'er dosya | 🟠 İkisi de yok, üstelik aynı iş |
| `pydantic-settings` | tsistem/config.py | 🟠 |
| `docx2pdf`, `pywin32` | doc_converter | 🟡 |

**`requirements.txt`'te var, hiç import edilmiyor (~3 GB):**
`sentence-transformers` (~2.5 GB torch ile) · `chromadb` (~250 MB) · `faiss-cpu` · `langchain` + `-community` + `-text-splitters` (~200 MB) · `scikit-learn` · `langdetect` · `jinja2` · `httpx` · `pytest` · `tqdm`

README'nin "FAISS / ChromaDB / HuggingFace Embeddings / LangChain" mimarisi **kodda hiç mevcut değil**. `similarity/embeddings.py` tamamen TODO stub:
```python
# TODO: Birhan tarafından Issue #3 kapsamında kodlanacak.
return [[0.0] * 384 for _ in texts]
```

---

### 4.6 🔴 DEMO / SAHTE VERİ ENVANTERİ

Kullanıcının en çok tekrarladığı ilke: *"demo olarak atanmış her şeyi sil, gerçek verilerle çalışacağız artık"* (#236).

#### Hâlâ aktif olan sahte veri

| # | Konum | İçerik | Etkilenen ekran |
|---|---|---|---|
| 1 | `ui/mock_data.py` (23 KB) | 48 sahte rapor, rastgele AI puanları, uydurma hakem isimleri, sahte benzerlik eşleşmeleri | `api_client.raporlar()` → **hakem paneli + dashboard** |
| 2 | `api/ui_adapter.py:43-55, 493, 581, 646` | `_mock_call` — DB boşsa mock'a düşüyor | **FastAPI "canlı" yanıtları** |
| 3 | `api_client.py:88-89` | Her rapor önce `mock_data._rapor()` ile üretiliyor, DB'den sadece 5 alan üzerine yazılıyor | Hakem ADIM 4-5 |
| 4 | `app.py:419-442` | TEKNOFEST takvim panosu — hardcoded HTML | Yarışmacı ana sayfa |
| 5 | `app.py:704-710` | "Ahmet Yılmaz (Üye)", "Prof. Dr. Mehmet (Danışman)" | Takımlarım |
| 6 | `app.py:1017-1022` | KVKK "✓ Onaylıdır / Aktif Üye" | Profil |
| 7 | `hakem.py:557-577` | Sabit takvim bandı, "Kalan: 23 Gün" | Hakem ADIM 1 |
| 8 | `hakem.py:861, 894, 900, 936` | Sabit `0.92` kategori uyumu, `uygun:True, sayfa:13`, `5/5 başlık`, **`%8` intihal** | Hakem ADIM 3 |
| 9 | `hakem.py:711-713, 1262` | PDF okunamazsa uydurma tek cümlelik rapor metni | AI girdisi |
| 10 | `hakem.py:774` | Sıfır kriterde `84.0` puan | Hakem ADIM 4 |
| 11 | `ui_adapter.py:356-369` | Her bölüm için "280 kelime / %95 doluluk / Yeterli" | Hakem ADIM 3 tablosu |
| 12 | `ui_adapter.py:673` | `referee_id="HAKEM-EMRE-1"` hardcoded | DB kaydı |
| 13 | `ui_adapter.py:628` | `for yarisma in ["hyz-otr-2026", "iyt-otr-2026"]` | Metrikler |
| 14 | `evaluator.py:501-527` | Heuristik sahte puanlar + sabit gerekçe/eksik şablonları | **Tüm AI değerlendirmeleri (LLM düşerse)** |
| 15 | `evaluator.py:551` | `confidence_score: 0.92` sabit | AI güven göstergesi |
| 16 | `chat_assistant.py:90-107` | Anahtar kelime `if/elif` — satır 100 rapordan bağımsız uydurma cevap, `status: SUCCESS` ile | Chat API |
| 17 | `spec_analyzer.py:81-129` | 4 sabit kural + sabit takvim | Admin AI kural çıkarıcı |
| 18 | `template_analyzer.py:73-179` | 14 uydurma rubrik kriteri | Admin AI rubrik çıkarıcı |
| 19 | `sartname_rehber.py:298-300` | Klasör adında "roket/iha/yapay/drone" geçiyorsa listeye **uydurma "KTR" ekliyor** | Aşama listeleri |
| 20 | `sartname_rehber.py:350-361, 643-660, 684-708` | Hardcoded zorunlu başlıklar, sayfa limitleri, kategori zorunlulukları | Hakem rehberi |
| 21 | `rubrik.py:11-116` | `HYZ_OTR_2026`, `IYT_OTR_2026`, `GERCEK_VAKA` | Hakem rubrik tablosu, karşılaştırma |
| 22 | `auth_service.py:121-151` | `admin@tsistem.org/admin123`, `hakem@tsistem.org/hakem123` — her açılışta **D1'e de** yazılıyor | Giriş |
| 23 | `app.py:446-447, 507-508` | `usr_hakem_ef6def`, `hakem@tsistem.org` fallback | Hakem paneli |
| 24 | `api_client.py:97, 119-121, 159-169` | "Prof. Dr. Ahmet Yılmaz", `sayfa_sayisi=13`, sabit bölüm→sayfa haritası | Hakem |
| 25 | `firebase_config.py:7-15` | Gerçek Firebase/Google OAuth kimlik bilgileri kaynak kodda | — |
| 26 | `data/takimlar.json` | Global takım dosyası — **tüm kullanıcılar aynı listeyi görüyor** | Takımlarım |
| 27 | `yarismaci.py:98-101, 273, 287` | `28.02.2026`, `15.04.2026`, `15.09.2026 - 20.09.2026` — **üç farklı yerde üç farklı uydurma tarih** | Vitrin, karne |
| 28 | `yonetici.py:104, 116-118, 251, 253, 392` | Aynı sabit tarihler | Admin formları |
| 29 | `yarismaci.py:228` | `team_id_val = ... or "100001"` hardcoded varsayılan takım | Karne |
| 30 | 4 ölü panel dosyası | "142 başvuru", "82.5/100", "%4.2 intihal", sahte intihal matrisi | (import edilmiyor) |

---

### 4.7 🟡 ÖLÜ KOD

**Ölü dosyalar (435 satır):** `ui/demo.py` · `views/yarismaci_paneli.py` · `views/hakem_paneli.py` · `views/yonetici_paneli.py`

**Ölü fonksiyonlar/sabitler:**
`theme.inject_css` · `theme.register_plotly_template` · `theme.FONT` · `.t3-navbar` CSS · `mock_data.GEREKCELER_KULLANILMIYOR` (27 satır) · `sartname_rehber.YARISMA_GRUPLARI` (63 satır) · `sartname_rehber.RUBRICS_DIR` · `sartname_rehber.pdf_sayfa_onizle` · `db.create_application` · `db.list_all_applications` · `db.get_all_referees` · `db.assign_referee_to_report` · `db.auto_distribute_reports` · `db.get_rubric_by_category` (1. tanım, 45 satır) · `db.list_assigned_reports_for_referee` · `db.save_competition`/`save_stage`/`get_competition_stages` (doğru olan sürümler!) · `auth_service.update_user_role`/`update_user_status` · `rubric_extractor._llm_extract` (50 satır) · `evaluator._HEURISTIC_SIGNALS` · `key_manager.self.index` · `api_client.yarismalar`/`analiz`/`rapor_yukle` · `auth_view.GOOGLE_SVG_ICON` · `auth_view.py:327-350` CSS (24 satır) · `hakem._kart` · `ui_adapter.upload_raporlar_ui` (stub) · `similarity/embeddings.py` (tamamı)

**Ölü importlar:** `yarismaci.py`'de 8 (`os`, `io`, `re`, `Path`, `typing`, `pandas`, `charts`, `karne_pdf`) · `yonetici.py`'de 6 · `hakem.py`'de 2 · `karsilastirma.py`'de 1

**Ölü UI elemanları:** `yarismaci.py:382` indirme butonu (no-op) · `yarismaci.py:167` `secili_seviye` (hiçbir yere yazılmıyor) · `app.py:312-313` boş menü kolonu · `app.py:562-563` erişilemez admin dalı · `start.py:85` `?demo=1` (kod yok)

---

## 5. KÖK NEDEN ANALİZİ — 5 SİSTEMİK DESEN

Yüzlerce bulgunun ardında beş tekrar eden hata deseni var. Bunlar düzeltilmezse yeni özellikler aynı hatalarla üretilmeye devam eder.

| # | Desen | Örnek sayısı | Sonuç |
|---|---|---|---|
| **D1** | **Sessiz yutma:** `except Exception: pass` + koşulsuz `return True` + koşulsuz `st.success()` | 40+ | Hiçbir yazma hatası kullanıcıya ulaşmıyor. Geliştirici "yaptım" sanıyor, veri kaybediliyor. |
| **D2** | **Çift implementasyon:** Aynı iş için iki metot, biri şemaya uygun diğeri değil; UI **yanlış olanı** çağırıyor | 6 (`save_competition`↔`upsert_competition`, `assign_referee_to_report`↔`assign_report_to_referee`, `get_rubric_by_category` ×2, iki R2 istemcisi, üç D1 istemcisi, iki CSS sistemi) | Doğru kod yazılmış ama kullanılmıyor. |
| **D3** | **Şema sözleşmesi yok:** SQL string'leri kodun içinde, şema `_init_sqlite()`'ta; ikisi bağımsız evrilmiş | 9 tablo | Yazma işlemleri çalışma zamanında patlıyor. |
| **D4** | **Fallback sahteyi gerçek gibi sunuyor:** LLM yoksa uydurma puan + `confidence 0.92`; DB boşsa mock; PDF okunamazsa uydurma metin | 8 | Kullanıcı sistemin çalıştığını sanıyor. **En tehlikeli desen.** |
| **D5** | **Sözleşmesiz anahtar eşleşmesi:** `file_name` vs `filename`, `max_pages` vs `maksimum_sayfa_siniri`, `stage` vs `stage_code`, `hedef_egitim_seviyesi` vs `target_level` | 7 | `.get()` sessizce `None`/varsayılan dönüyor → ekranda `None` veya sabit değer. |

**Önerilen kalıcı çözüm:** Faz 0'da bir **"sözleşme katmanı"** kurulacak — Pydantic modelleri + tek şema kaynağı + hata fırlatan repository katmanı. Bu, D1/D3/D5'i yapısal olarak imkânsız kılar.

---

## 6. HEDEF MİMARİ

### 6.1 Cloudflare topolojisi

```
┌─────────────────────────────────────────────────────────────┐
│                     KULLANICI (Tarayıcı)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS
                ┌───────────▼───────────┐
                │  Streamlit (Container)│  ← Cloudflare Containers / VM
                │  src/ui/**            │     (Workers'ta çalışamaz)
                └───────────┬───────────┘
                            │ Python fonksiyon çağrısı
                ┌───────────▼───────────┐
                │  Repository Katmanı   │  ← YENİ: src/data/repo/*.py
                │  (tek veri kapısı)    │     Pydantic modelleri, hata fırlatır
                └─────┬───────────┬─────┘
                      │           │
         ┌────────────▼──┐   ┌────▼──────────────┐
         │ D1Client      │   │ R2Client          │
         │ (tek istemci) │   │ (tek istemci)     │
         │ requests+retry│   │ boto3 s3v4+path   │
         └────────┬──────┘   └────┬──────────────┘
                  │               │
        ┌─────────▼─────┐  ┌──────▼─────────────────────┐
        │ Cloudflare D1 │  │ Cloudflare R2 (t-sistem)   │
        │ 14 tablo      │  │ + Public custom domain     │
        │ schema.sql    │  │   veya presigned URL       │
        └───────────────┘  └────────────────────────────┘
```

**Kararlar:**
- **Streamlit Workers/Pages'te çalışamaz** (uzun ömürlü WebSocket gerekir). UI Cloudflare Containers'ta veya bir VM'de barındırılacak; **D1 + R2 buluttan kullanılacak.** Bu, kullanıcının "her şey Cloudflare'de olsun" isteğinin gerçekçi karşılığıdır.
- **KV, Vectorize, Workers AI şimdilik kapsam dışı** — mevcut mimari bunları gerektirmiyor; Vectorize ileride benzerlik motoru için değerlendirilebilir (Faz 8).
- **FastAPI korunacak** ama Streamlit'in tek veri kapısı **Repository katmanı** olacak; ikili yol ortadan kalkacak.

### 6.2 D1 şeması (14 tablo)

`db/schema.sql` olarak yazılacak ve `wrangler d1 execute t-sistem --file=db/schema.sql --remote` ile uygulanacak. **Aynı dosya yerel SQLite için de kullanılacak** — tek şema kaynağı.

```sql
-- ============ KİMLİK ============
CREATE TABLE IF NOT EXISTS auth_users (
  user_id TEXT PRIMARY KEY,
  username TEXT, name TEXT NOT NULL, surname TEXT,
  email TEXT UNIQUE NOT NULL, password_hash TEXT,
  role TEXT NOT NULL DEFAULT 'yarismaci'
       CHECK(role IN ('yarismaci','hakem','admin')),
  institution TEXT, department TEXT, graduation_status TEXT,
  tc_citizen TEXT, gender TEXT, birth_date TEXT, phone TEXT,
  address TEXT, education_level TEXT, specialty TEXT,
  auth_provider TEXT DEFAULT 'local',
  profile_completed INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'aktif' CHECK(status IN ('aktif','pasif')),
  created_at TEXT NOT NULL, updated_at TEXT
);
-- NOT: eski `users` tablosu KALDIRILACAK, auth_users tek kaynak.

-- ============ YARIŞMA ============
CREATE TABLE IF NOT EXISTS competitions (
  competition_id TEXT PRIMARY KEY,        -- = slug
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,              -- ON CONFLICT hedefi
  domain TEXT NOT NULL,                   -- Havacılık, Yapay Zeka, ...
  sub_category TEXT,
  levels TEXT,                            -- "Lise, Üniversite"
  description TEXT,                       -- kullanıcı #270: yarışma amacı
  logo_url TEXT,                          -- R2 key
  sartname_url TEXT,                      -- R2 key (birincil/birleşik)
  schedule_json TEXT,                     -- {son_basvuru, yarisma_tarihi, sonuc_tarihi}
  awards_json TEXT,
  publish_status TEXT NOT NULL DEFAULT 'taslak'
       CHECK(publish_status IN ('taslak','yayinda','kapali')),
  created_at TEXT NOT NULL, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS competition_specs (   -- YENİ: çok şartnameli yarışmalar
  spec_id TEXT PRIMARY KEY,
  competition_id TEXT NOT NULL,
  title TEXT NOT NULL,                    -- "Mesleki Yetenek - Yazılım Dalı"
  branch_code TEXT,                       -- alt dal (9 dallı yarışmalar için)
  r2_key TEXT NOT NULL,
  page_count INTEGER,
  is_primary INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (competition_id) REFERENCES competitions(competition_id)
);

CREATE TABLE IF NOT EXISTS competition_stages (
  stage_id TEXT PRIMARY KEY,
  competition_id TEXT NOT NULL,
  stage_code TEXT NOT NULL,               -- OTR, KTR, FTR, ODR, PDR, TTR, ...
  stage_name TEXT NOT NULL,
  level TEXT DEFAULT 'Genel',             -- Lise / Üniversite / Ortaokul / Genel
  sablon_docx_url TEXT,
  sablon_pdf_url TEXT,
  max_pages INTEGER DEFAULT 25,
  max_score REAL DEFAULT 100.0,
  deadline TEXT,
  font_and_margins TEXT,
  required_sections_json TEXT,
  order_index INTEGER DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT,
  UNIQUE(competition_id, stage_code, level),
  FOREIGN KEY (competition_id) REFERENCES competitions(competition_id)
);

CREATE TABLE IF NOT EXISTS competition_requirements (   -- şartnameden AI ile çıkarılan
  req_id TEXT PRIMARY KEY,
  competition_id TEXT NOT NULL,
  spec_id TEXT,
  rule_type TEXT NOT NULL
       CHECK(rule_type IN ('takim','danisman','teknik','katilim','dil','diger')),
  title TEXT NOT NULL,
  description TEXT,
  min_team_size INTEGER, max_team_size INTEGER,
  advisor_required INTEGER DEFAULT 0,
  target_level TEXT,
  is_mandatory INTEGER DEFAULT 1,
  source_quote TEXT,                      -- şartnamedeki dayanak cümle
  approved_by_admin INTEGER DEFAULT 0,    -- admin onayladı mı
  created_at TEXT NOT NULL, updated_at TEXT,
  FOREIGN KEY (competition_id) REFERENCES competitions(competition_id)
);

CREATE TABLE IF NOT EXISTS stage_rubric_criteria (      -- YENİ AD (çakışma çözümü)
  criterion_id TEXT PRIMARY KEY,
  competition_id TEXT NOT NULL,
  stage_code TEXT NOT NULL,
  level TEXT DEFAULT 'Genel',
  criterion_code TEXT NOT NULL,           -- C1, C2, ...
  criterion_name TEXT NOT NULL,
  description TEXT,
  max_score REAL NOT NULL,
  parent_code TEXT,                       -- alt kriter desteği (Algoritmalar>Veri Setleri)
  order_index INTEGER DEFAULT 0,
  source_quote TEXT,
  approved_by_admin INTEGER DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT,
  UNIQUE(competition_id, stage_code, level, criterion_code)
);
-- NOT: eski `competition_rubrics` FastAPI rubric sistemi için ayrı kalır veya migrate edilir.

-- ============ TAKIM & BAŞVURU ============
CREATE TABLE IF NOT EXISTS teams (
  team_id TEXT PRIMARY KEY,               -- uuid4
  team_code TEXT NOT NULL UNIQUE,         -- davet kodu (6 hane, kararlı)
  name TEXT NOT NULL,
  level TEXT,                             -- Ortaokul/Lise/Üniversite  (#274)
  institution TEXT,
  captain_user_id TEXT NOT NULL,
  advisor_name TEXT, advisor_email TEXT,
  status TEXT NOT NULL DEFAULT 'aktif',
  created_at TEXT NOT NULL, updated_at TEXT,
  FOREIGN KEY (captain_user_id) REFERENCES auth_users(user_id)
);
-- Kullanıcı #270: takımlar bir yarışmaya BAĞLANMAZ.

CREATE TABLE IF NOT EXISTS team_members (
  team_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role_in_team TEXT NOT NULL DEFAULT 'uye'
       CHECK(role_in_team IN ('kaptan','uye','danisman')),
  joined_at TEXT NOT NULL,
  PRIMARY KEY (team_id, user_id),
  FOREIGN KEY (team_id) REFERENCES teams(team_id),
  FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
);

CREATE TABLE IF NOT EXISTS applications (
  app_id TEXT PRIMARY KEY,                -- uuid4
  team_id TEXT NOT NULL,
  competition_id TEXT NOT NULL,
  level TEXT,
  status TEXT NOT NULL DEFAULT 'aktif'
       CHECK(status IN ('aktif','geri_cekildi','elendi','tamamlandi')),
  created_at TEXT NOT NULL, updated_at TEXT,
  UNIQUE(team_id, competition_id),
  FOREIGN KEY (team_id) REFERENCES teams(team_id),
  FOREIGN KEY (competition_id) REFERENCES competitions(competition_id)
);

-- ============ RAPOR & DEĞERLENDİRME ============
CREATE TABLE IF NOT EXISTS reports (
  report_id TEXT PRIMARY KEY,             -- uuid4
  app_id TEXT NOT NULL,
  competition_id TEXT NOT NULL,
  stage_code TEXT NOT NULL,
  level TEXT DEFAULT 'Genel',
  version INTEGER NOT NULL DEFAULT 1,     -- revizyon desteği
  file_name TEXT NOT NULL,                -- insan okunabilir ad
  r2_key TEXT NOT NULL,                   -- SADECE key (URL değil)
  page_count INTEGER,
  report_text TEXT,
  status TEXT NOT NULL DEFAULT 'BEKLEMEDE'
       CHECK(status IN ('BEKLEMEDE','HAKEME_ATANDI','DEGERLENDIRILIYOR',
                        'DEGERLENDIRILDI','REVIZYON_ISTENDI','REDDEDILDI')),
  security_json TEXT, checks_json TEXT,
  ai_score REAL, ai_data_json TEXT,
  feedback_json TEXT,
  created_at TEXT NOT NULL, updated_at TEXT,
  UNIQUE(app_id, stage_code, level, version),
  FOREIGN KEY (app_id) REFERENCES applications(app_id)
);

CREATE TABLE IF NOT EXISTS report_assignments (
  assignment_id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  referee_user_id TEXT NOT NULL,
  assigned_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ATANDI'
       CHECK(status IN ('ATANDI','INCELENIYOR','TAMAMLANDI','IPTAL')),
  assigned_at TEXT NOT NULL,
  completed_at TEXT,
  UNIQUE(report_id, referee_user_id),
  FOREIGN KEY (report_id) REFERENCES reports(report_id),
  FOREIGN KEY (referee_user_id) REFERENCES auth_users(user_id)
);

CREATE TABLE IF NOT EXISTS evaluations (          -- YENİ: hakem kararı ayrı tabloda
  evaluation_id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  referee_user_id TEXT NOT NULL,
  total_score REAL NOT NULL,
  ai_total_score REAL,
  decision TEXT NOT NULL
       CHECK(decision IN ('KABUL','REVIZYON','RET')),
  referee_notes TEXT,
  spec_compliance_json TEXT,              -- ADIM 3 hakem kararları
  sealed_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT,
  UNIQUE(assignment_id),
  FOREIGN KEY (assignment_id) REFERENCES report_assignments(assignment_id)
);

CREATE TABLE IF NOT EXISTS evaluation_scores (    -- YENİ: kriter bazlı kırılım
  evaluation_id TEXT NOT NULL,
  criterion_code TEXT NOT NULL,
  criterion_name TEXT NOT NULL,
  max_score REAL NOT NULL,
  ai_score REAL,
  referee_score REAL NOT NULL,
  ai_rationale TEXT,
  referee_rationale TEXT,
  evidence_json TEXT,                     -- TÜM kanıt alıntıları (#202)
  PRIMARY KEY (evaluation_id, criterion_code),
  FOREIGN KEY (evaluation_id) REFERENCES evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS report_cards (         -- YENİ: karne, başvuruya bağlı (#270)
  card_id TEXT PRIMARY KEY,
  app_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  evaluation_id TEXT NOT NULL,
  total_score REAL NOT NULL,
  strengths_json TEXT,
  improvements_json TEXT,
  roadmap_json TEXT,
  pdf_r2_key TEXT,
  published_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (app_id) REFERENCES applications(app_id)
);

CREATE TABLE IF NOT EXISTS calibration_settings (
  key TEXT PRIMARY KEY, value REAL NOT NULL,
  description TEXT, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (            -- YENİ
  log_id TEXT PRIMARY KEY,
  actor_user_id TEXT, action TEXT NOT NULL,
  entity_type TEXT, entity_id TEXT,
  before_json TEXT, after_json TEXT,
  created_at TEXT NOT NULL
);

-- İndeksler
CREATE INDEX IF NOT EXISTS idx_reports_app     ON reports(app_id);
CREATE INDEX IF NOT EXISTS idx_reports_comp    ON reports(competition_id, stage_code);
CREATE INDEX IF NOT EXISTS idx_assign_referee  ON report_assignments(referee_user_id, status);
CREATE INDEX IF NOT EXISTS idx_apps_team       ON applications(team_id);
CREATE INDEX IF NOT EXISTS idx_members_user    ON team_members(user_id);
CREATE INDEX IF NOT EXISTS idx_rubric_lookup   ON stage_rubric_criteria(competition_id, stage_code, level);
CREATE INDEX IF NOT EXISTS idx_specs_comp      ON competition_specs(competition_id);
```

### 6.3 R2 klasör hiyerarşisi

Kullanıcının #221 ve #289'daki isteğine göre, **insan okunabilir isimlendirmeyle**:

```
t-sistem/
├── logos/
│   └── {competition_slug}.png
├── yarismalar/
│   └── {competition_slug}/
│       ├── sartname/
│       │   ├── {slug}_sartnamesi.pdf                    # tek şartnameli (50 yarışma)
│       │   └── {slug}_{dal_kodu}_sartnamesi.pdf         # çok dallı (4 yarışma)
│       └── asamalar/
│           └── {STAGE_CODE}/                            # OTR, KTR, FTR, ODR...
│               ├── sablon/
│               │   ├── {slug}_{stage}_{seviye}_rapor_sablonu.docx
│               │   └── {slug}_{stage}_{seviye}_rapor_sablonu.pdf   # otomatik üretilen
│               └── raporlar/
│                   └── {app_id}/
│                       └── {takim_slug}_{slug}_{stage}_raporu_v{n}.pdf
└── karneler/
    └── {app_id}/
        └── {takim_slug}_{slug}_{stage}_karnesi.pdf
```

**Veri seti gerçekleri** (`data/competition_migration_plans.json`'dan doğrulandı):

| Ölçüt | Dağılım |
|---|---|
| Toplam yarışma | **60** |
| Şartname sayısı | 1 şartname: **50** · 0 şartname: **6** · 3 şartname: **1** · 7 şartname: **2** · 9 şartname: **1** |
| Aşama sayısı | 1 aşama: **40** · 2 aşama: **18** · 3 aşama: **2** |
| Aşama kodları | OTR 25 · ODR 15 · KTR 12 · PDR 4 · TYF/TTR/PSR 3'er · DTR/AHR/FDR 2'şer · FTR/DDR/TYR/OAR/ATR/PVT 1'er |
| Seviye | Genel **217** · Lise 6 · Ortaokul 1 · Üniversite 1 · Serbest Girişimci 1 |

**Çok şartnameli 4 yarışma için karar (kullanıcının #289'daki açık sorusu):**
`teknofest-mesleki-yetenek-yarismasi` (9 dal), `hyperloop-gelistirme-yarismasi` (7), `uluslararasi-elektrikli-arac-yarislari` (7), `yapay-zeka-dil-ajanlari-yarismasi` (3).

> **Öneri: birleştirme YAPILMAMALI.** Her şartname `competition_specs` tablosunda ayrı satır, `branch_code` ile etiketlenir. AI kural çıkarımı **dal bazında** çalışır; `competition_requirements.spec_id` hangi daldan geldiğini taşır. Yarışmacı başvururken dalı seçer, uygunluk kontrolü yalnızca o dalın kurallarıyla yapılır. Birleştirme, birbiriyle çelişen takım limitlerini ve teknik isterleri karıştırır — kullanıcının *"hiçbirinin birbiriyle karışmadan"* isteğine aykırı olur.

**`SABLON` ve `YARISMACI_RAPORLARI` sahte aşama kodları** (2'şer adet) migration'da temizlenecek — bunlar klasör adı, aşama değil.

**0 şartnameli 6 yarışma** `publish_status='taslak'` ile yüklenecek, admin panelinde "Şartname Bekleniyor" rozetiyle görünecek.

### 6.4 Repository katmanı (yeni)

```
src/data/
├── schema.sql              # TEK şema kaynağı (D1 + SQLite)
├── client.py               # D1Client — tek istemci, requests + retry + log
├── r2.py                   # R2Client — tek istemci, presigned + public URL
├── models.py               # Pydantic: Competition, Stage, Team, Application, Report...
├── enums.py                # ReportStatus, Decision, RuleType, TeamRole (TEK kaynak)
├── migrate.py              # schema.sql'i D1'e ve SQLite'a uygular
└── repo/
    ├── competitions.py     # CompetitionRepo
    ├── teams.py
    ├── applications.py
    ├── reports.py
    ├── evaluations.py
    └── users.py
```

**Repository sözleşmesi (zorunlu kurallar):**
1. Her metot Pydantic modeli alır/döndürür — dict yok
2. **Hata fırlatır**, `except: pass` yok — UI `st.error` gösterir
3. `bool` döndürmez; oluşturulan/güncellenen nesneyi döndürür
4. Tüm ID'ler `uuid4()` — `hash()` yasak
5. Tüm enum'lar `enums.py`'den — string literal yasak

---

## 7. FAZ FAZ UYGULAMA PLANI

> Her fazın sonunda **kabul kriteri** var. Kriter sağlanmadan sonraki faza geçilmez.

---

### FAZ 0 — GÜVENLİK VE TEMİZLİK (1 gün)

| # | Görev | Dosya |
|---|---|---|
| 0.1 | Tüm anahtarları iptal et ve yenile (§1.1) | Cloudflare/Anthropic/OpenAI/Groq/Google panelleri |
| 0.2 | Google bypass bloğunu kaldır | `views/auth_view.py:74-93` sil |
| 0.3 | OAuth: `state` CSRF + ID token `iss`/`aud`/`exp` doğrulaması | `auth_service.py:156-186` |
| 0.4 | `clientSecret`'ı `.env`'e taşı | `ui/firebase_config.py:15` |
| 0.5 | `redirect_uri`'yi `.env`'den oku (localhost hardcode kaldır) | `auth_view.py:33, 55` |
| 0.6 | `argon2-cffi` ile şifre hash'i + mevcut hash'ler için geçiş | `auth_service.py:31-33` |
| 0.7 | Seed hesapları `TSISTEM_BOOTSTRAP=1` + `.env` şifresi arkasına al | `auth_service.py:121-151` |
| 0.8 | FastAPI JWT auth; header varsayılan `"ADMIN"` kaldır | `security/auth.py:26-61` |
| 0.9 | `CORS_ALLOWED_ORIGINS` zorunlu, `"*"` kaldır | `main.py:66-76` |
| 0.10 | `.gitignore` güncelle; repo geçmişini temizle | `.gitignore` |
| 0.11 | **4 ölü panel dosyasını sil** | `demo.py`, `*_paneli.py` ×3 |
| 0.12 | Ölü importları temizle (17 adet) | `yarismaci.py`, `yonetici.py`, `hakem.py`, `karsilastirma.py` |
| 0.13 | `requirements.txt`: eksik 8 paketi ekle, kullanılmayan ~3 GB'ı çıkar | `requirements.txt` |
| 0.14 | `db.py:1002-1046` çift tanımlı metodu sil | `database/db.py` |

**Kabul:** `?google_email=` ile giriş yapılamıyor · `curl` ile header'sız admin ucuna erişilemiyor · `pip install -r requirements.txt` sonrası tüm importlar çözülüyor · repo boyutu <100 MB.

---

### FAZ 1 — VERİ KATMANI YENİDEN İNŞASI (3-4 gün) ⭐ **EN KRİTİK FAZ**

| # | Görev | Çıktı |
|---|---|---|
| 1.1 | `src/data/schema.sql` yaz (§6.2, 14 tablo) | Yeni dosya |
| 1.2 | `src/data/enums.py` — `ReportStatus`, `Decision`, `RuleType`, `TeamRole`, `PublishStatus` | Yeni dosya |
| 1.3 | `src/data/models.py` — 12 Pydantic modeli | Yeni dosya |
| 1.4 | `src/data/client.py` — **tek** `D1Client`: `requests` + 3 retry + exponential backoff + `success:false` yakalama + **hata fırlatma** + structured log | Yeni dosya |
| 1.5 | `src/data/r2.py` — **tek** `R2Client`: `upload`, `download_bytes`, `delete`, `presigned_url(ttl)`, `public_url` | Yeni dosya |
| 1.6 | `src/data/migrate.py` — `schema.sql`'i D1'e ve SQLite'a uygular; `--verify` modu tablo/kolon karşılaştırması yapar | Yeni dosya |
| 1.7 | 6 repository sınıfı yaz | `src/data/repo/*.py` |
| 1.8 | **`_sync_to_cloudflare_d1`'deki 7 kolonlu `CREATE TABLE reports`'u sil** (yanlış şemayı kalıcılaştırıyor) | `db.py:629-639` |
| 1.9 | `db.py`'deki `execute_d1` bloğunu (satır 1341-1772) **tamamen kaldır**; çağıranları repository'ye yönlendir | `db.py` |
| 1.10 | `auth_service._query_d1`'i `D1Client`'a devret | `auth_service.py:43-66` |
| 1.11 | `auth_service.authenticate` indeks kayması hatasını düzelt (`row[13]`→`row[15]` vb.) | `auth_service.py:273-277` |
| 1.12 | `utils/storage.py`'yi sil, `r2_service.py`'yi `R2Client`'a devret | 2 dosya |
| 1.13 | R2 public erişim: custom domain bağla veya presigned URL'e geç; `.env`'e `CLOUDFLARE_R2_PUBLIC_URL` ekle | Cloudflare paneli + `.env` |
| 1.14 | `sartname_rehber.py:51, 246` → `download_file` → `download_bytes` | `sartname_rehber.py` |
| 1.15 | Tüm `abs(hash(...))` → `uuid.uuid4()` (5 yer) | `yarismaci.py`, `app.py`, `db.py` |
| 1.16 | **13 `except Exception: pass` bloğunu kaldır**, hata fırlat + `st.error` | `db.py` |

**Kabul:**
- `python -m src.data.migrate --verify` → D1 ve SQLite'ta 14 tablo, kolonlar birebir aynı
- Bir yarışma oluştur → D1'de `SELECT` ile görünüyor
- Kasten bozuk bir INSERT dene → ekranda **kırmızı hata** çıkıyor, "başarılı" yazmıyor

---

### FAZ 2 — VERİ MİGRASYONU: 60 YARIŞMA (2-3 gün)

Kaynak: `C:\Users\mehme\OneDrive\Desktop\teknofest_yarismalar` + `data/competition_migration_plans.json` (hazır envanter).

| # | Görev |
|---|---|
| 2.1 | `scripts/migrate_to_cloud.py` yaz — dry-run modu zorunlu |
| 2.2 | Dosya adlarını sunucu uyumlu hale getir: küçük harf, Türkçe karakter yok, boşluk yok (kullanıcı #251) — ama **DB'de insan okunabilir `title` sakla** (#255) |
| 2.3 | 60 yarışmayı `competitions`'a yaz (`publish_status='taslak'`) |
| 2.4 | Şartnameleri R2'ye yükle + `competition_specs`'e yaz (çok dallılar `branch_code` ile) |
| 2.5 | `SABLON` / `YARISMACI_RAPORLARI` sahte aşama kodlarını ele; gerçek 17 aşama kodunu `competition_stages`'e yaz |
| 2.6 | Seviye tespiti: `detected_level` alanını `competition_stages.level`'a taşı |
| 2.7 | Şablon DOCX'lerini R2'ye yükle |
| 2.8 | Yarışma logolarını `data/logos/`'tan R2'ye taşı |
| 2.9 | Migrasyon raporu üret: yarışma × şartname × aşama × şablon matrisi, eksikler listesi |

**Kabul:** D1'de 60 `competitions`, ~110 `competition_stages`, ~85 `competition_specs` kaydı · R2'de doğru hiyerarşi · rapor dosyasında 0 "atlandı" satırı (kullanıcının #218'deki *"67 şartname atlandı"* şikâyeti kapanıyor).

---

### FAZ 3 — TEMA BİRLEŞTİRME (2 gün)

> Kullanıcının #231'deki isteği: **"giriş yap kayıt ol kısmındaki renk paletine uygun olarak temayı yeniden düzenle"**

**Adım 3.0 — Tek satırlık en yüksek getirili değişiklik:**

```python
# app.py, st.set_page_config'ten HEMEN SONRA:
import theme
theme.inject_css(st)
theme.register_plotly_template()
```
ve **`app.py:136-233` arasındaki 98 satırlık CSS bloğunu sil** (Inter `@import` satırı `theme.CSS`'e taşınır).

Bu tek değişiklik şunları anında düzeltir: üst toolbar gizlenir (#34, #275) · taban font 16.5px olur (#246) · sayfa zemini `#F4F6F9` olur · **tüm primary butonlar turuncu olur** (#35, #37, #129, #137) · sekmeler pill görünümüne geçer · input'lar dolgulu olur (#206). **Görsel farkların ~%80'i tek hamlede kapanır.**

| # | Görev | Dosya |
|---|---|---|
| 3.1 | Adım 3.0 (yukarıda) | `app.py` |
| 3.2 | `.streamlit/config.toml` oluştur: `base="light"`, `primaryColor="#F04823"`, `secondaryBackgroundColor="#F4F6F9"` | Yeni dosya |
| 3.3 | İki paralel renk setini birleştir; çakışan yeşil/kırmızı/lacivert için tek değer seç | `theme.py:13-54` |
| 3.4 | Ölçek token'ları ekle: `RADIUS`, `SPACE`, `SHADOW`, `FONT_SIZE`, `WEIGHT` (750/850 → 700/800) | `theme.py` |
| 3.5 | CSS'i `:root { --color-primary: ... }` custom property'lerine çevir; `@media (prefers-color-scheme: dark)` bloğu ekle | `theme.py:74-399` |
| 3.6 | **`components.py`'nin 12 tanımsız `ts-*` sınıfını `theme.CSS`'e ekle** (veya `t3-*`'a taşı) — puan çubuğu, pill, tile görünür olur | `theme.py` + `components.py` |
| 3.7 | `auth_view.py:274-351` CSS bloğunu **sil** → **"Kayıt Ol sekmesinde buton kırmızıya dönüyor" hatası kökten çözülür** | `auth_view.py` |
| 3.8 | `auth_view.py:148-192` iki aynalı sekme bloğunu tek `.t3-segment-btn--active` sınıfına indirge (45→12 satır) | `auth_view.py` |
| 3.9 | `auth_view.py:327-350` ölü CSS'i ve `GOOGLE_SVG_ICON` ölü sabitini sil | `auth_view.py` |
| 3.10 | 7× tekrarlanan `<hr>` → `.t3-sep`; 7× bölüm başlığı → `.t3-form-section`; 3× başlık bloğu → `_auth_header()` | `auth_view.py`, `app.py` |
| 3.11 | Kart dilini eşitle: auth'ta `st.container(border=True)` yerine `.t3-content-card` | `auth_view.py:117, 630` |
| 3.12 | Navbar'ı `.t3-navbar` sınıfıyla sar (sınıf zaten var, kullanılmıyor) | `app.py:253-352` |
| 3.13 | `hakem.py:317-327` CSS bloğunu `theme.CSS`'e taşı | `hakem.py` |
| 3.14 | `charts.py:145` `#d03b3b` → `theme.STATUS["kritik"]`; fallback kopyalarını kaldır | `charts.py` |
| 3.15 | `_get_logo_base64`'e `@st.cache_data` ekle; logo boyutlarını tek ölçeğe indir | `app.py:86-90` |
| 3.16 | Lint kuralı: `theme.py:13-54` dışında hex kodu yasak (bugün 137 ihlal) | CI |
| 3.17 | Test: kodda kullanılan her CSS sınıfı tanımlı mı? (bugün 12 tanımsız yakalanırdı) | CI |

**Kabul:** Giriş ekranı, kayıt ekranı, şifre sıfırlama ve ana uygulama **aynı buton rengi, aynı input dolgusu, aynı kart radius'u, aynı font ölçeği** kullanıyor · Streamlit üst şeridi görünmüyor · `grep -c 'inject_css'` ≥ 2.

---

### FAZ 4 — YARIŞMACI AKIŞI (3 gün)

| # | Görev |
|---|---|
| 4.1 | **Takımları D1'e taşı** — `teams` + `team_members`; `data/takimlar.json`'ı sil (#249) |
| 4.2 | Takım kodu: `uuid4`'ten türetilen 6 haneli **kararlı** kod; katılırken **gerçek doğrulama** |
| 4.3 | Takım seviyesi seçimi (Ortaokul/Lise/Üniversite) — #274 |
| 4.4 | Takım üyeleri gerçek `team_members`'tan; hardcoded isimleri sil (`app.py:704-710`) |
| 4.5 | Danışman ekleme (şartname zorunlu kılıyor) |
| 4.6 | **Gerçek başvuru akışı**: vitrin butonu → `ApplicationRepo.create()` → `applications` tablosu |
| 4.7 | Uygunluk kontrolü: `competition_requirements`'tan takım büyüklüğü / danışman / seviye doğrulaması |
| 4.8 | **Deadline kontrolü** — süresi geçmiş aşamaya yükleme engellenir |
| 4.9 | Vitrin: `levels` kolonu artık var → **seviye filtresi çalışır**; `tr_norm()` ile Türkçe arama |
| 4.10 | Vitrin: **kalan gün rozeti** (`schedule_json` parse + `datetime` farkı); hardcoded `28.02.2026` kaldır |
| 4.11 | Vitrin: yarışma kartı tıklanabilir → detay (açıklama, ödüller, şartname indir) |
| 4.12 | Logo: R2'den (`download_bytes` düzeltildi) → placeholder yerine gerçek logo |
| 4.13 | Rapor yükleme: **`success` kontrolü**, gerçek hata mesajı, `r2_key` (URL değil) kaydı, `uuid4` id |
| 4.14 | İki kopya yükleme yolunu (Tab2 + Tab3) **tek fonksiyona** indir |
| 4.15 | `st.form` içindeki dinamik selectbox sorununu çöz (yarışma değişince aşamalar güncellenmiyor) |
| 4.16 | Mükerrer yükleme → `version` artırımı; revizyon akışı |
| 4.17 | **Gizlilik:** `SELECT * FROM reports` → `WHERE app_id IN (kullanıcının takımlarının başvuruları)` |
| 4.18 | `stage_code` None çökmesi: `(r.get("stage_code") or "").upper()` |
| 4.19 | **KARNE:** `report_cards` + `evaluation_scores`'tan gerçek karne — kriter kırılımı, radar grafiği, güçlü yönler, gelişim önerileri (#272) |
| 4.20 | Karne PDF indirme — `karne_pdf.uret(rapor, yarisma)` doğru imzayla + `feedback/generator.generate_feedback_pdf` bağlantısı |
| 4.21 | Rapor indirme butonu → `st.download_button` + `presigned_url` |
| 4.22 | Başvurularım: yarışma bazında gruplama, aşama bazında durum, **kaptan ek rapor yükleyebilir**, tarihler görünür (#273) |
| 4.23 | Takım üyelerinin hepsinde aynı takım/başvuru görünür (#273) |
| 4.24 | KVKK rozetini gerçek `profile_completed`/onay alanına bağla |
| 4.25 | Ana sayfa hardcoded takvimini → seçili/başvurulan yarışmaların gerçek `schedule_json`'ından üret |
| 4.26 | i18n: `views/yarismaci.py`'nin tüm stringlerini `t()`'ye taşı |

**Kabul:** Sıfırdan bir yarışmacı kayıt olur → takım kurar → yarışmaya başvurur → rapor yükler → hakem puanlar → **karnesini kriter kırılımıyla görür ve PDF indirir.** Uçtan uca, hiçbir sahte veri olmadan.

---

### FAZ 5 — HAKEM AKIŞI VE İZOLASYON (3 gün)

| # | Görev |
|---|---|
| 5.1 | **`db.py:758-760`'daki delik filtreyi sil** → `report_assignments` JOIN ile katı izolasyon |
| 5.2 | `list_assigned_reports_for_referee`'yi (repository sürümü) fiilen kullan |
| 5.3 | `api_client.raporlar()` → `referee_id` gönder; `ui_adapter` bunu filtrele |
| 5.4 | **`api_client.py:88-89`'daki mock harmanlamasını kaldır** — DB verisi yoksa boş, mock yok |
| 5.5 | `ui_adapter.py`'deki `_mock_call` fallback'ini kaldır; DB boşsa 404/boş liste |
| 5.6 | `ui_adapter.py:356-369` uydurma bölüm doluluk verisini kaldır |
| 5.7 | **Mühürleme tek yazım:** `api_client.hakem_karari_gonder` çağrısını kaldır; `EvaluationRepo.seal()` kullan |
| 5.8 | `referee_id="HAKEM-EMRE-1"` hardcode'unu sil (`ui_adapter.py:673`) |
| 5.9 | **Kriter bazlı puanları `evaluation_scores`'a yaz** — denetim izi |
| 5.10 | Hakem notu geri yükleme (`referee_notes` anahtarını tüm yollarda üret) |
| 5.11 | **Manuel puan girişi + tavan/taban kontrolü** (#204): slider yanında `number_input`, `0 ≤ puan ≤ max_score` doğrulaması, ikisi senkronize |
| 5.12 | `rubrik.getir()` fallback'ini kaldır → **gerçek `stage_rubric_criteria` sorgusu**; kategori seçimine göre doğru rubrik |
| 5.13 | **İntihal:** `run_all_checks`'e `corpus` geçir (aynı yarışma+aşamadaki diğer raporlar) → sabit %8 kalkar |
| 5.14 | `hakem.py:711-713` uydurma rapor metnini kaldır → PDF okunamazsa **açık hata** göster, AI çalıştırma |
| 5.15 | `weighted_total_score`'u Pydantic şemasına ekle → kalibrasyon UI'a ulaşsın; `84.0` fallback'ini kaldır |
| 5.16 | `hakem.py:851-852, 884, 925` anahtar uyuşmazlıklarını tek sözleşmeye bağla (`max_pages`, `font_and_margins`, `target_level`) |
| 5.17 | `runner.py:145-165` sabit 5 başlık fallback'ini kaldır → gerçek `required_sections_json` |
| 5.18 | Karne PDF butonu: `uret(rapor, yarisma)` doğru imza |
| 5.19 | ADIM 1 sabit takvim bandını → gerçek `competition_stages.deadline` |
| 5.20 | **Chat asistanını hakem paneline bağla** — ADIM 2 yanına "Rapora Soru Sor" kutusu |
| 5.21 | `chat_assistant.py:90-107` sahte fallback'i kaldır → LLM yoksa açık uyarı |
| 5.22 | Ana sayfa metriklerini `report_assignments`'tan üret → **sayı tutarsızlıkları biter** (#106, #119, #125, #127) |
| 5.23 | i18n: `views/hakem.py` (1316 satır, 0 `t()`) |

**Kabul:** Hakem A, hakem B'ye atanmış raporu **göremiyor** · atanmamış rapor **hiçbir hakemde görünmüyor** · ana sayfadaki sayı ile listedeki sayı **birebir aynı** · intihal oranı raporlara göre **değişiyor** · AI çalışmadan hiçbir puan gösterilmiyor.

---

### FAZ 6 — ADMIN FULL CRUD (3 gün)

> Kullanıcının 4 kez tekrarladığı ister: **"admin gördüğü her şeyi düzenleyebilir ekleyebilir silebilir, tam yetki onda olmalı"**

| # | Görev |
|---|---|
| 6.1 | Tüm admin CRUD'unu repository'ye taşı — `upsert_*` yerine repository metotları |
| 6.2 | **Yarışma oluştur/düzenle/sil** gerçekten çalışsın (Faz 1 şeması ile) |
| 6.3 | Takvim: `text_input` → `st.date_input`; `sonuc_tarihi` kaybı düzelt (kısmi güncelleme) |
| 6.4 | **Her yarışmanın bağımsız takvimi** (#256) + aşama bazında `deadline` |
| 6.5 | Şartname yükleme: `success` kontrolü; `domain`/`levels`/`description` **ezilmesin** (kısmi update) |
| 6.6 | Çok şartnameli yarışmalar: `competition_specs` yönetimi, dal ekleme/silme |
| 6.7 | Kural editörü: `selectbox(index=0)` sabitini düzelt → `rule_type` korunsun |
| 6.8 | **`st.data_editor` ile canlı düzenlenebilir kural tablosu** (kullanıcının istediği) |
| 6.9 | Aşama ekleme/**düzenleme**/silme + seviye bazlı şablonlar |
| 6.10 | Rubrik editörü: toplam puan hesabı silinenleri saymasın; alt kriter desteği (`parent_code`) |
| 6.11 | **"Kaydet" butonu ile toplu kayıt** — otomatik kayıt yerine (#276) |
| 6.12 | **Hakem havuzu:** `surname` kolonu eklendi → liste doluyor; uzmanlık, mevcut yük, tamamlanma oranı |
| 6.13 | **Rapor havuzu:** `file_name` kolonu düzeltildi → liste doluyor; yarışma/aşama/durum filtreleri |
| 6.14 | **Rapor yönlendirme:** `report_assignments`'a gerçek yazma; **çoklu hakem** ataması |
| 6.15 | Atama geri alma / yeniden atama |
| 6.16 | `auto_distribute_reports`'u butona bağla (otomatik dengeli dağıtım) |
| 6.17 | **Kalibrasyon paneli** — `routes.py:658-729` uçlarını UI'a bağla |
| 6.18 | Yarışma durumu: taslak / yayında / kapalı (`publish_status`) |
| 6.19 | Sonuç ilanı + sıralama + ödül yönetimi (`awards_json`) |
| 6.20 | **Denetim izi** (`audit_log`) — kim, neyi, ne zaman |
| 6.21 | Silme onayı (yazarak doğrulama) + R2 dosyalarının da silinmesi (`delete_file` kullanılsın) |
| 6.22 | Sayfalama (`list_all_*` tüm satırları çekiyor) |
| 6.23 | Excel/CSV dışa aktarma |
| 6.24 | **Rol kontrolü:** `app.py:316, 485` `else:` → `elif rol in ("admin",)`; `yonetici` rolünü kaldır veya tanımla |
| 6.25 | `yonetici.py` ve `admin_kullanicilar.py` başına modül içi rol guard |
| 6.26 | Ana admin'in rolü/durumu değiştirilemesin |
| 6.27 | `guard.SecurityGuard`'ı Streamlit yükleme akışlarına da bağla (şu an yalnız FastAPI'de) |
| 6.28 | i18n: `views/yonetici.py`, `admin_kullanicilar.py`, `dashboard.py`, `karsilastirma.py` |

**Kabul:** Admin yeni yarışma oluşturur → şartname yükler → AI kural çıkarır → kuralları düzenler → **"Kaydet"e basar** → D1'de görünür → aşama ekler → şablon yükler → AI rubrik çıkarır → puanları ayarlar → kaydeder → raporu hakeme yönlendirir → **hakem panelinde o rapor görünür.** Uçtan uca.

---

### FAZ 7 — GERÇEK AI MOTORU (3-4 gün)

> Kullanıcının en net kavramsal kuralı (#102): *"Kategori zorunluluklarını şartnameden çıkar. Rapor zorunluluklarını rapor şablonundan çıkar. **İKİSİ AYRI ŞEYLER, ASLA BİR ARADA TUTULMAMALI.**"*

| # | Görev |
|---|---|
| 7.1 | **Model ID'lerini düzelt:** `claude-sonnet-4-6` → geçerli Anthropic model ID'si |
| 7.2 | `groq` paketini ekle → 2. katman canlansın |
| 7.3 | `OPENAI_API_KEYS` çoğulunu `key_manager`'a bağla; Groq'u da `key_manager`'a taşı |
| 7.4 | `key_manager`: **429/5xx ile 401/404/parse hatasını ayır**; sadece rate-limit'te failover; exponential backoff; anahtar sağlık takibi |
| 7.5 | **`spec_analyzer.py`'yi gerçek LLM'e bağla** — şartname metni → yapılandırılmış kural JSON'u (`source_quote` zorunlu) |
| 7.6 | `spec_analyzer.py:62` `or "lise" in low_text` mantık hatasını kaldır |
| 7.7 | **`template_analyzer.py`'yi gerçek LLM'e bağla** — şablon DOCX metni + tablolar → kriter + **puan** JSON'u; hardcoded 14 kriteri sil |
| 7.8 | Alt kriter desteği (kullanıcının #220'deki örneği: Algoritmalar 30 → Veri Setleri 10 / Algoritmalar 15 / Akış Şeması 5) |
| 7.9 | `rubric_extractor._llm_extract`'i **fiilen çağır**; `heuristic_extract`'i yalnızca LLM tamamen düşerse ve **açık uyarıyla** kullan |
| 7.10 | **`_generate_smart_heuristic_evaluation`'ın sahte puanlamasını kaldır.** LLM düşerse: puan verme, `status: AI_UNAVAILABLE` döndür, ekranda **"AI değerlendirmesi yapılamadı"** göster |
| 7.11 | `confidence_score: 0.92` sabitini kaldır → gerçek güven veya `None` |
| 7.12 | **ADIM 3 promptu** (#215): şartname zorunlulukları + yarışmacı raporu → uygunluk raporu. Yalnız ADIM 3 verisi |
| 7.13 | **ADIM 4 promptu** (#216): o aşamanın rapor şablonu (kriter + puan) + yarışmacı raporu → kriter bazlı puan + gerekçe + **kanıt** |
| 7.14 | ADIM 3 ve ADIM 4 **ayrı ayrı tetiklenebilir** olsun (#198, #199) |
| 7.15 | **Kanıt: TÜM alıntılar** (#202) — ilk değil hepsi; kriter bazında ayrı (#204) |
| 7.16 | **Kanıtlanamayan kriterler** için "rapor genelinde yorum" modu (#178, #179) — AI kendisi karar versin |
| 7.17 | Katman 2 (fact-checker) korunacak ve güçlendirilecek: sayfa numarası + karakter aralığı döndürsün |
| 7.18 | Katman 3 (synthesizer): rubrik toplamıyla tutarlılık, kalibrasyon, `weighted_total_score` |
| 7.19 | AI çıktıları `reports.ai_data_json` + `evaluation_scores.evidence_json`'a kaydedilsin — **her rerun'da yeniden çağrı yapılmasın** |
| 7.20 | **"Toplu AI Ön Kontrolü Başlat"** — admin panelinde batch + ilerleme çubuğu (#136) |
| 7.21 | Hakem notunu AI ile yazma (#195) — `generate_ai_referee_note` zaten var, fallback'i düzelt |
| 7.22 | Prompt'lara `guard.neutralize_prompt_injection` uygulanmaya devam etsin |

**Kabul:** Aynı rapor iki kez değerlendirildiğinde tutarlı puan · farklı yarışmaların rubrikleri **farklı** · kullanıcının #220'de yapıştırdığı ÖTR puan tablosu (Takım Şeması / Mevcut Durum 10 / Algoritmalar 30 / Özgünlük 10 / Takvim 10 / Sonuçlar 30 / Kaynakça 5 / Genel Düzen 5) **birebir** çıkıyor · LLM kapalıyken **hiçbir puan üretilmiyor**, açık uyarı çıkıyor · her kriterin kendi kanıt alıntıları var.

---

### FAZ 8 — DOKÜMAN GÖRÜNTÜLEME (2 gün)

| # | Görev |
|---|---|
| 8.1 | **`doc_converter`'a LibreOffice yolu ekle:** `soffice --headless --convert-to pdf --outdir` — Linux/Docker'da çalışır (docstring'in zaten vaat ettiği) |
| 8.2 | Dönüşüm başarısızsa **açık hata** — sahte "başarıyla dönüştürüldü" mesajını kaldır |
| 8.3 | Türkçe karakter sorunu: LibreOffice yolu bunu çözer (font gömme) — Docker imajına `fonts-dejavu`, `fonts-liberation` ekle |
| 8.4 | **Tek görüntüleme yolu:** DOCX → otomatik PDF → PDF viewer. İki seçenek kaldırılır (#242, #244) |
| 8.5 | `docx_gorunum.py:407` hardcoded Office viewer URL'ini kaldır |
| 8.6 | **PDF viewer: zoom + serbest kaydırma** (#230, #245) — `pdf.js` tabanlı bileşen veya PyMuPDF + ölçek slider'ı |
| 8.7 | Sayfa sayfa yükleme yerine sürekli kaydırma; sayfa önbelleği |
| 8.8 | İndirme: hem **PDF** hem **Word (.docx)** seçeneği (#255) — presigned URL ile |
| 8.9 | İnsan okunabilir dosya adları: `{takim}_{yarisma}_{asama}_raporu.pdf` |

**Kabul:** Admin DOCX yükler → otomatik PDF üretilir → yarışmacı ve hakem kesintisiz önizler, **zoom yapabilir** → hem PDF hem Word indirebilir · Türkçe karakterler kutu çıkmıyor.

---

### FAZ 9 — DOĞRULAMA, TEST, DEPLOY (2 gün)

| # | Görev |
|---|---|
| 9.1 | **Şema doğrulama testi:** kodda geçen her tablo/kolon `schema.sql`'de var mı? (bugün 9 ihlal yakalanırdı) |
| 9.2 | **Enum testi:** yazılan her status/decision değeri `enums.py`'de var mı? (bugün 4 ihlal) |
| 9.3 | **CSS sınıf testi:** kullanılan her sınıf tanımlı mı? (bugün 12 ihlal) |
| 9.4 | **Hex lint:** `theme.py` token bölgesi dışında hex yasak (bugün 137 ihlal) |
| 9.5 | **i18n testi:** her `t()` anahtarı sözlükte var mı? Hardcoded Türkçe string taraması |
| 9.6 | **Ölü kod testi:** import edilmeyen modül / çağrılmayan public fonksiyon raporu |
| 9.7 | **`except: pass` yasağı** — CI'da grep ile engelle |
| 9.8 | Uçtan uca senaryo testi: admin yarışma açar → yarışmacı başvurur → rapor yükler → admin atar → hakem puanlar → yarışmacı karne görür |
| 9.9 | Rol izolasyon testi: hakem A, hakem B'nin raporunu göremez; yarışmacı başkasının raporunu göremez |
| 9.10 | Yük testi: 60 yarışma × 100 rapor ile sayfa açılış süreleri |
| 9.11 | Dockerfile: Python + LibreOffice + fontlar; Cloudflare Containers / VM deploy |
| 9.12 | `.env.example` + kurulum dokümanı |

---

## 8. ZAMAN ÇİZELGESİ

| Faz | Süre | Bağımlılık | Kritiklik |
|---|---|---|---|
| 0 — Güvenlik ve temizlik | 1 gün | — | 🔴 Zorunlu, ilk |
| 1 — Veri katmanı | 3-4 gün | Faz 0 | 🔴 Her şeyin temeli |
| 2 — 60 yarışma migrasyonu | 2-3 gün | Faz 1 | 🔴 |
| 3 — Tema birleştirme | 2 gün | — (paralel yürütülebilir) | 🟠 |
| 4 — Yarışmacı akışı | 3 gün | Faz 1, 2 | 🔴 |
| 5 — Hakem + izolasyon | 3 gün | Faz 1, 2 | 🔴 |
| 6 — Admin full CRUD | 3 gün | Faz 1, 2 | 🔴 |
| 7 — Gerçek AI motoru | 3-4 gün | Faz 1, 2, 6 | 🔴 |
| 8 — Doküman görüntüleme | 2 gün | Faz 1 | 🟠 |
| 9 — Test ve deploy | 2 gün | Hepsi | 🟠 |

**Toplam: ~24-27 iş günü.** Faz 3 (tema) diğerlerine paralel yürütülebilir → **~22-25 gün.**

**Hızlı kazanım sırası (ilk 3 gün için):**
1. Faz 0.2 — güvenlik açığını kapat (30 dk)
2. Faz 3.0 — `theme.inject_css(st)` ekle (10 dk, görsel farkın %80'i)
3. Faz 1.1-1.6 — şema + tek istemci (1 gün, tüm CRUD'u canlandırır)
4. Faz 5.1 — hakem izolasyonu (1 saat)
5. Faz 7.10 — sahte AI puanlamasını kapat (30 dk, güven kritik)

---

## 9. KARAR BEKLEYEN SORULAR

Bunlar planı uygulamaya başlamadan netleşmesi gereken noktalar:

| # | Soru | Öneri |
|---|---|---|
| 1 | **Çok şartnameli 4 yarışmada** (9/7/7/3 dal) şartnameler birleştirilsin mi? | **Hayır** — `competition_specs` + `branch_code` ile ayrı tutulsun (§6.3 gerekçesi) |
| 2 | #291'deki *"OTR olmayan yarışmaya OTR raporu kısmı ekle"* ne demek? | İki okuması var: (a) OTR aşaması olmayan yarışmalara varsayılan bir OTR aşaması eklensin, (b) her yarışmaya "ön rapor" adında genel bir aşama açılsın. **Netleştirilmeli.** |
| 3 | `users` tablosu ile `auth_users` birleştirilsin mi? | **Evet** — `auth_users` tek kaynak, `users` kaldırılsın (`specialty` kolonu `auth_users`'a taşınsın) |
| 4 | FastAPI korunacak mı yoksa Streamlit doğrudan repository mi kullansın? | **Repository tek kapı**; FastAPI dış entegrasyonlar ve batch işler için kalsın |
| 5 | R2 public erişim: custom domain mi, presigned URL mi? | **Presigned URL** (güvenli, ek DNS yapılandırması gerektirmez); logolar için public custom domain düşünülebilir |
| 6 | Benzerlik motoru: mevcut `difflib` mi, Cloudflare Vectorize mi? | Faz 8'e kadar `difflib` yeterli; 500+ rapor sonrası Vectorize |
| 7 | Streamlit nerede barındırılacak? | Cloudflare Containers veya küçük bir VM — Workers/Pages **çalışamaz** |
| 8 | 0 şartnameli 6 yarışma ne olacak? | `publish_status='taslak'`, admin panelinde "Şartname Bekleniyor" rozeti |

---

## 10. EK: KRİTİK BULGULARIN HIZLI REFERANSI

| # | Bulgu | Dosya:Satır | Etki |
|---|---|---|---|
| 1 | Şifresiz admin bypass | `auth_view.py:74-93` | 🔴 Tam sistem ele geçirme |
| 2 | FastAPI RBAC varsayılanı `"ADMIN"` | `security/auth.py:27` | 🔴 Tüm admin uçları açık |
| 3 | `.env` + `firebase_config.py` canlı sırlar | — | 🔴 13 anahtar ifşa |
| 4 | Hakem izolasyonu delinmiş | `db.py:758-760` | 🔴 Her hakem her raporu görüyor |
| 5 | 3 tablo hiç yaratılmıyor | `db.py` | 🔴 Atama/başvuru/kural kaybediliyor |
| 6 | Aynı tabloya iki şema | `db.py` | 🔴 4 tabloda yazma çalışmıyor |
| 7 | 40+ `except: pass` | Tüm proje | 🔴 Hatalar görünmez |
| 8 | AI fallback içerikten bağımsız puan veriyor | `evaluator.py:501-504` | 🔴 Boş rapor 87/100 alır |
| 9 | `src/ai/` LLM kullanmıyor | `spec_analyzer.py`, `template_analyzer.py` | 🔴 "AI kural/rubrik çıkarımı" sahte |
| 10 | Yarışmacı puanını hiç göremiyor | `yarismaci.py:324` ↔ `db.py:797` | 🔴 Karne akışı kopuk |
| 11 | `theme.inject_css` hiç çağrılmıyor | `theme.py:402` | 🟠 325 satır CSS ölü |
| 12 | Kayıt sekmesinde buton rengi değişiyor | `auth_view.py:295-311` | 🟠 Tema tutarsızlığı |
| 13 | İntihal sabit %8 | `hakem.py:936` | 🔴 Kontrol hiç çalışmıyor |
| 14 | `hash()` ile ID üretimi | 5 yer | 🔴 Yeniden başlatmada ID değişiyor |
| 15 | Word→PDF Linux'ta çalışmıyor | `doc_converter.py` | 🟠 + sahte başarı mesajı |
| 16 | `download_file` metodu yok | `sartname_rehber.py:51, 246` | 🟠 R2 indirme hiç çalışmıyor |
| 17 | R2 public URL üretilmiyor | `r2_service.py:90`, `storage.py:48` | 🟠 Dosyalar açılamıyor |
| 18 | Rubrik tablosu hep HYZ ÖTR | `rubrik.py:74` | 🔴 Yanlış kriterler gösteriliyor |
| 19 | Mühürlemede çift yazım | `hakem.py:1290-1301` | 🔴 Hakem kimliği eziliyor |
| 20 | Kriter puanları kaydedilmiyor | `db.py:797` | 🔴 Denetim izi yok |
| 21 | Yarışmacı tüm raporları görüyor | `yarismaci.py:234` | 🔴 Gizlilik ihlali |
| 22 | `stage_code` None → çökme | `yarismaci.py:280` | 🟠 Sekme çöküyor |
| 23 | 4.000 satırda 0 `t()` çağrısı | `views/*` | 🟠 Dil desteği yarım |
| 24 | ~3 GB kullanılmayan bağımlılık | `requirements.txt` | 🟠 Deploy engeli |
| 25 | 435 satır ölü panel dosyası | 4 dosya | 🟡 Karışıklık |

---

*Bu plan, `T-Sistem` kod tabanının tamamının, geçmiş 294 mesajlık geliştirme konuşmasının ve mevcut veri setinin birlikte incelenmesiyle hazırlanmıştır. Faz sıralaması, bağımlılık grafiğine ve risk ağırlığına göre belirlenmiştir.*
