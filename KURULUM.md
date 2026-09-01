# T-SİSTEM · KURULUM

> **Anahtarlarınız aynı kalıyor.** Mevcut `.env` dosyanıza dokunulmuyor;
> Cloudflare, Anthropic, Groq ve OpenAI anahtarlarınız olduğu gibi kullanılır.
> Mevcut `admin@tsistem.org` / `hakem@tsistem.org` hesapları ve parolaları da
> aynen çalışır — sistem ilk girişte parola şifrelemesini sessizce güçlendirir,
> sizden hiçbir şey istemez.

---

## Hızlı yol: iki komut

```bash
pip install -r requirements.txt
python kur.py --uygula
```

`kur.py` şunları kendisi yapar:

1. Python sürümünü ve paketleri kontrol eder
2. `.env` dosyanızı okur → **eksik olan yeni değişkenleri ekler**, mevcutlara dokunmaz
   (önce `.env.env.yedek` adıyla yedek alır)
3. Word → PDF motorunu kontrol eder
4. Cloudflare D1 ve R2 bağlantısını test eder
5. **Cloudflare'deki eski tablolarınızı yeni şemaya taşır** — veri kaybı olmadan
6. 20 tabloluk şemayı uygular ve doğrular
7. Hesaplarınızı ve yarışma sayınızı gösterir, sırada ne olduğunu söyler

Değişiklik yapmadan sadece durumu görmek isterseniz `--uygula` olmadan çalıştırın.

Sonra:

```bash
streamlit run src/ui/app.py
```

---

## Kurulumun ne yaptığı — adım adım

### 1 · Paketler

Eski `requirements.txt` yanlıştı: kodun kullandığı **9 paket listede yoktu**
(`python-docx`, `groq`, `Pillow`, `mammoth`, `pypdf`…), buna karşılık kodun hiç
kullanmadığı **~3 GB paket** listedeydi (`sentence-transformers`, `chromadb`,
`faiss-cpu`, `langchain`). Yeni liste bunu düzeltiyor.

### 2 · `.env` — anahtarlarınıza dokunulmaz

`kur.py` yalnızca **yeni kodun ihtiyaç duyduğu ve sizde olmayan** değişkenleri
ekler. Eklenenler:

| Değişken | Ne işe yarar |
|---|---|
| `TSISTEM_DB_BACKEND=d1` | Verinin Cloudflare D1'den okunacağını söyler |
| `CLOUDFLARE_R2_PUBLIC_URL` | **Custom domain adresinizi buraya yazın.** Boş kalırsa sistem otomatik presigned URL üretir — yine çalışır |
| `TSISTEM_JWT_SECRET` | FastAPI oturum imzası; otomatik üretilir |
| `TSISTEM_ANTHROPIC_MODEL` | Eski koddaki model kimliği (`claude-sonnet-4-6`) **geçersizdi**, her istekte 404 dönüyordu. Doğrusu yazılır |
| `TSISTEM_GROQ_MODEL`, `TSISTEM_OPENAI_MODEL`, `TSISTEM_LLM_ORDER` | Sağlayıcı sırası ve modelleri |
| `TSISTEM_SIMILARITY_MODE=hybrid` | İntihal: birebir kopya + anlamsal, ikisi birden |
| `TSISTEM_EMBEDDING_MODEL`, `CLOUDFLARE_VECTORIZE_INDEX` | Anlamsal benzerlik |
| `TSISTEM_OAUTH_REDIRECT`, `CORS_ALLOWED_ORIGINS` | Google girişi ve API adresleri |

### 3 · Word → PDF

Eski kod Linux'ta **hiçbir zaman** PDF üretemiyordu ama yine de "başarıyla
dönüştürüldü" diyordu. Artık LibreOffice headless kullanılıyor ve başarısızlık
açıkça bildiriliyor.

- **Windows'ta**: Microsoft Word kuruluysa ek bir şey gerekmez.
  Değilse [libreoffice.org](https://www.libreoffice.org/) kurun.
- **Linux/Docker**: `sudo apt-get install -y libreoffice-writer fonts-dejavu fonts-liberation`

> Türkçe karakterlerin kutu çıkma sorunu (sizin #132'deki şikâyetiniz) bu
> yolla çözüldü — `ÇĞİÖŞÜ çğıöşü` test edilip doğrulandı.

### 4 · Cloudflare'deki eski tablolarınız

Bu en önemli adım. Cloudflare D1'inizde şu an **eski** tablolar var:

| Tablo | Sorun | Ne yapılır |
|---|---|---|
| `auth_users` | `surname`, `specialty`, `updated_at` kolonları yok | `ALTER TABLE ADD COLUMN` — **veri korunur** |
| `competitions` | `levels`, `logo_r2_key`, `publish_status`, `spec_status` yok | `ALTER` — veri korunur |
| `competition_stages` | 8 kolon eksik | `ALTER` — veri korunur |
| `reports` | `app_id`, `file_name`, `r2_key` gibi **NOT NULL** kolonlar eklenemez | `reports_eski_<tarih>` olarak **yeniden adlandırılır**, temiz tablo açılır. Eski veriniz durur, silinmez |
| `users`, `categories`, `competition_rubrics`, `category_requirements`, `report_template_requirements` | Artık kullanılmıyor | Dokunulmaz, sadece listelenir |
| 13 yeni tablo | Yok | Oluşturulur |

Önce ne olacağını görmek için:

```bash
python -m src.data.migrate --upgrade
```

Uygulamak için `--upgrade --apply`. `kur.py --uygula` bunu zaten yapar.

### 5 · Hesaplarınız

`admin@tsistem.org` ve `hakem@tsistem.org` **mevcut parolalarıyla** çalışmaya
devam eder. Sistem eski saltsız SHA-256 hash'ini tanır, doğrular ve ilk başarılı
girişte Argon2'ye yükseltir. Sizin yapmanız gereken bir şey yok.

Yeni hesapları admin panelindeki *Kullanıcılar* ekranından açabilirsiniz.

---

## Yarışma verisini yükleme

Veritabanınız şu an boş (0 yarışma). 60 yarışmayı taşımak için:

```bash
# ÖNCE kuru çalıştırma — hiçbir şey yazmaz, tam rapor üretir
python scripts/migrate_dataset.py ^
    --source "C:\Users\mehme\OneDrive\Desktop\teknofest_yarismalar" ^
    --plan data/competition_migration_plans.json ^
    --report data/migrasyon_raporu.md

# Raporu inceleyin, sonra uygulayın
python scripts/migrate_dataset.py --source ... --plan ... --apply
```

Beklenen: **60 yarışma · 76 şartname · 84 aşama**.
Tek yarışmayla denemek için: `--only teknofest-mesleki-yetenek-yarismasi`

Çok dallı yarışmalar (Mesleki Yetenek 9 dal, Hyperloop 7, Elektrikli Araç 7,
Dil Ajanları 3) **birleştirilmez** — her dal `branch_code` ile ayrı tutulur.

---

## İsteğe bağlı temizlik

```bash
python scripts/cleanup_dead_code.py            # önce listeler
python scripts/cleanup_dead_code.py --apply    # _silinenler_<tarih>/ klasörüne taşır
```

Hiçbir yerden çağrılmayan `demo.py`, üç sahte panel dosyası, `mock_data.py`,
TODO stub `embeddings.py`, ikinci R2 istemcisi ve global `data/takimlar.json`
taşınır. Silinmez, taşınır — istediğinizde geri alabilirsiniz.

---

## Testler

```bash
python -m pytest tests/ -q
```

**20 test** geçmelidir. Bunlar eski kod tabanındaki beş sistemik hatayı
yapısal olarak engeller: şema uyuşmazlığı, enum kaosu, sessiz hata yutma,
tanımsız CSS sınıfı, arayüze sahte veri sızması.

---

## İlk kullanım sırası

1. **Admin** ile giriş yapın (mevcut parolanız) → *Yönetim* → *Yarışma Yönetim İstasyonu*
2. Bir yarışmaya girin → *Şartname* sekmesi → PDF yükleyin → **"AI ile Kuralları Çıkar"**
3. Çıkan kuralları tabloda düzenleyin → **"Kaydet"** → **"Onayla"**
4. *Aşamalar* sekmesi → aşama ekleyin → Word şablonu yükleyin (PDF otomatik üretilir)
   → **"AI ile Rubriği Çıkar"** → puanları ayarlayın → **"Kaydet"** → **"Onayla"**
5. *Genel* sekmesinden yayın durumunu **"yayında"** yapın
6. **Yarışmacı** hesabıyla girin → vitrinde yarışmayı görün → takım kurun → başvurun → rapor yükleyin
7. **Admin** → *Hakem & Rapor Havuzu* → raporu hakeme atayın (veya *Otomatik Dengeli Dağıt*)
8. **Hakem** ile girin → 5 adımı yürütün → mühürleyin
9. **Yarışmacı** hesabına dönün → *Başvurularım* → **karne görünür**

---

## Sorun giderme

| Belirti | Sebep / çözüm |
|---|---|
| `D1'e baglanilamadi` | `CLOUDFLARE_API_TOKEN` yetkileri: `D1:Edit` ve `Workers R2 Storage:Edit` olmalı |
| `no such column: surname` | Adım 4'ü çalıştırmadınız → `python kur.py --uygula` |
| `no such table: teams` | Aynı — şema uygulanmamış |
| **"AI degerlendirmesi yapilamadi"** | **Bu doğru davranıştır.** Sistem artık LLM ulaşılamazken uydurma puan üretmiyor. `.env`'deki model adlarını ve anahtarları kontrol edin |
| "yönetici henüz rubrik onaylamamış" | Adım 4'ü (şablon → AI rubrik → Kaydet → Onayla) tamamlayın |
| "karşılaştırılacak başka rapor yok" | **Doğru.** İntihal için aynı yarışma+aşamada ikinci rapor gerekir. Eski koddaki sabit %8 kaldırıldı |
| PDF'te Türkçe karakter kutu | `fonts-dejavu fonts-liberation` eksik (Linux) |
| Şablon yüklendi ama PDF yok | LibreOffice / Word kurulu değil — artık açık hata veriyor |
| Dosyalar açılmıyor | `CLOUDFLARE_R2_PUBLIC_URL` boş veya yanlış; boşsa presigned URL devreye girer |

---

## Kalan işler

| İş | Not |
|---|---|
| `src/database/db.py` | FastAPI rotaları hâlâ kullanıyor. Streamlit artık kullanmıyor |
| `dashboard.py`, `karsilastirma.py`, `admin_kullanicilar.py` | Henüz eski katmanda; çalışıyorlar ama repository'ye taşınmalı |
| E-posta bildirimi | `notifications` tablosu hazır, SMTP gönderimi bağlanmadı |
| Cloudflare Vectorize | Anlamsal intihal için: `wrangler vectorize create t-sistem-raporlar --dimensions=1024 --metric=cosine` (opsiyonel — literal katman zaten çalışır) |
