# 🎯 T-Sistem — Ekip Görev Dağılımı ve GitHub Issue Şablonları

Bu doküman, **T3 Vakfı Yapay Zekâ Creathonu (Problem 4: TEKNOFEST Yapay Zekâ Destekli Değerlendirme Sistemi)** için ekip üyelerinin (**Mehmet**, **Birhan**, **Emre**) üstleneceği görevleri, mantıksal mimari gereksinimlerini, UI/UX standartlarını ve GitHub'da doğrudan Issue (Görev Kartı) olarak açılabilecek hazır şablonları içerir.

---

# 👥 EKİP GÖREV VE SORUMLULUK ÖZETİ

```
                    ┌─────────────────────────────────────────────────────────┐
                    │               T-SİSTEM ÇÖZÜM MİMARİSİ                   │
                    └─────────────────────────────────────────────────────────┘
                                                │
         ┌──────────────────────────────────────┼──────────────────────────────────────┐
         ▼                                      ▼                                      ▼
┌──────────────────┐                  ┌──────────────────┐                  ┌──────────────────┐
│   BİRHAN (NLP)   │                  │  MEHMET (AI/API) │                  │  EMRE (UI/UX)    │
├──────────────────┤                  ├──────────────────┤                  ├──────────────────┤
│• PDF Loader & OCR│                  │• FastAPI Backend │                  │• Hakem Paneli    │
│• Dil & Şablon    │ ───────────────► │• Rubric Evaluation│ ───────────────► │• Yarışmacı Karne │
│• Başlık Kontrolü │ (Temizlenmiş Metin│• AI 4. Göz Prompt │   (REST API JSON  │• Admin Dashboard │
│• FAISS Benzerlik │  & Benzerlikler) │• JSON Schemas    │     Responses)   │• Modern Tema     │
└──────────────────┘                  └──────────────────┘                  └──────────────────┘
```

---

# 📌 GİTHUB ISSUE ŞABLONLARI (Kopyala & Yapıştır)

Aşağıdaki başlıkları doğrudan GitHub deponuzun **Issues -> New Issue** kısmına kopyalayıp ilgili ekip arkadaşınıza atayabilirsiniz.

---

## 🟢 BİRHAN İÇİN ISSUE'LAR (Veri Pipeline, NLP, Kural Motoru & Benzerlik)

### 📋 Issue #1: PDF Ayrıştırma, Metin Çıkarma ve Ön İşleme Modülü (Ingestion)
**Atanan:** `@Birhan`  
**Etiketler:** `backend`, `data-pipeline`, `nlp`, `priority:critical`

#### 🎯 Amaç:
Yarışmacıların sisteme yüklediği tekli veya çoklu PDF raporlarını hatasız ayrıştırarak metin, başlık hiyerarşisi, sayfa düzeni ve tablo verilerini temiz JSON formatında belleğe aktarmak.

#### 🛠️ Nasıl Yapılacak (Teknik Adımlar):
1. `src/ingestion/pdf_loader.py` dosyasını oluşturun.
2. `PyMuPDF (fitz)` veya `pdfplumber` kullanarak PDF sayfalarını döngüye alın.
3. PDF bozuk veya salt taranmış resim (scanned) ise `pdfplumber` başarısız olursa yedek metin çıkarma (`Tesseract OCR` veya fallback exception) mekanizması ekleyin.
4. `src/ingestion/preprocessor.py` içerisinde metindeki anlamsız boşlukları, tireleme hatalarını temizleyin ve LangChain `RecursiveCharacterTextSplitter` ile 500-1000 tokenlık parçalara (chunks) bölün.

#### ✅ Kabul Kriterleri (Definition of Done):
- [ ] 20+ sayfalık örnek TEKNOFEST raporunu <2 saniyede okuyup JSON döndürmeli.
- [ ] Tablolar, başlıklar ve paragraflar birbirinden ayrıştırılmalı.
- [ ] Türkçe karakter bozulması (ş, ğ, ı, ü, ö, ç) sıfır olmalı.

---

### 📋 Issue #2: Dil, Şablon ve Zorunlu Başlık Uygunluk Kontrolörü (Checkers)
**Atanan:** `@Birhan`  
**Etiketler:** `nlp`, `validation`, `rules`, `priority:high`

#### 🎯 Amaç:
Raporun dilini tespit etmek, TEKNOFEST resmi rapor şablonuna (font boyutu, sayfa sınırı, marjinler) uyumunu kontrol etmek ve zorunlu başlıkların (`Özet`, `Problem Tanımı`, `Yöntem`, `Yenilikçi Yön`, `Uygulanabilirlik`, `Kaynaklar`) raporda bulunup bulunmadığını ve doluluk oranını denetlemek.

#### 🛠️ Nasıl Yapılacak (Teknik Adımlar):
1. `src/checkers/language_checker.py`: `langdetect` kütüphanesini kullanarak rapor dilini (`tr` / `en`) tespit edin. Şartnamede istenen dil ile eşleşmiyorsa hata bayrağı üretin.
2. `src/checkers/template_checker.py`: PDF'in sayfa sayısını, kenar boşluklarını ve başlık yazı tipi boyutlarını analiz edin. Şablon dışı formatları tespit edin.
3. `src/checkers/section_checker.py`: Zorunlu başlık listesini regex ve semantik benzerlik ile raporda tarayın. Başlık var mı? Altındaki paragraf boş mu veya 50 kelimeden az mı? Kontrol edin.

#### ✅ Kabul Kriterleri (Definition of Done):
- [ ] Çıktı şu formatta JSON üretmeli:
  ```json
  {
    "language": {"detected": "tr", "is_valid": true},
    "template": {"page_count": 12, "max_allowed": 15, "is_valid": true, "font_warning": false},
    "sections": {
      "ozet": {"exists": true, "word_count": 180, "status": "OK"},
      "butce_plani": {"exists": false, "word_count": 0, "status": "MISSING"}
    }
  }
  ```

---

### 📋 Issue #3: Vektör Veritabanı ve Benzerlik / İntihal Analizi Motoru
**Atanan:** `@Birhan`  
**Etiketler:** `nlp`, `embeddings`, `vector-db`, `similarity`, `priority:critical`

#### 🎯 Amaç:
Sisteme yüklenen tüm raporları embedding vektörlerine dönüştürerek vektör veritabanında saklamak; başvurular arasında veya geçmiş projelerle yüksek benzerlik (%70+) gösteren kısımları bularak hakeme "Benzerlik Riski" uyarısı üretmek.

#### 🛠️ Nasıl Yapılacak (Teknik Adımlar):
1. `src/similarity/embeddings.py`: `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2` veya OpenAI `text-embedding-3-small`) ile metinleri 384/1536 boyutlu vektörlere dönüştürün.
2. `src/similarity/vector_store.py`: `FAISS` veya `ChromaDB` kullanarak lokal vektör indeksi oluşturun.
3. Yeni bir rapor geldiğinde mevcut diğer tüm raporlarla kosinüs benzerliği (`cosine similarity`) hesaplayın.
4. %70 üzeri benzerlik tespit edildiğinde en çok benzeşen paragrafları ve eşleşen rapor ID'sini eşleştirin.

#### ✅ Kabul Kriterleri (Definition of Done):
- [ ] 100 raporluk bir havuzda <500ms içinde en benzer 3 raporu getirmeli.
- [ ] Hakeme gösterilmek üzere eşleşen cümlelerin/bölümlerin metin alıntılarını vermeli.

---

## 🔵 MEHMET İÇİN ISSUE'LAR (Backend, API, AI Kriter Motoru & Prompt Mühendisliği)

### 📋 Issue #4: FastAPI Çekirdek Backend Mimarisi ve Veri Modelleri
**Atanan:** `@Mehmet`  
**Etiketler:** `backend`, `fastapi`, `architecture`, `priority:critical`

#### 🎯 Amaç:
Frontend ile AI/NLP modülleri arasındaki iletişimi sağlayacak, rol bazlı (Yarışma Yöneticisi, Hakem, Yarışmacı) endpoint'leri sunan sağlam bir REST API kurmak.

#### 🛠️ Nasıl Yapılacak (Teknik Adımlar):
1. `src/api/schemas.py`: Pydantic ile `ReportUploadResponse`, `EvaluationResult`, `RefereeDecisionRequest`, `FeedbackResponse` şemalarını oluşturun.
2. `src/api/routes.py`: Aşağıdaki temel endpoint'leri yazın:
   * `POST /api/reports/upload`: Çoklu PDF yükleme ve analiz başlatma.
   * `GET /api/reports/{id}/analysis`: Dil, şablon, başlık, benzerlik ve AI analiz sonuçlarını getirme.
   * `POST /api/referee/evaluate`: Hakemin nihai puan ve onayını kaydetme.
   * `GET /api/contestant/feedback/{id}`: Yarışmacı karnesini getirme.
   * `GET /api/admin/metrics`: Canlı değerlendirme istatistikleri.
3. CORS middleware ve hata yakalama (`Global Exception Handler`) mekanizmalarını kurun.

#### ✅ Kabul Kriterleri (Definition of Done):
- [ ] Swagger dokümantasyonu (`/docs`) üzerinden tüm endpoint'ler test edilebilmeli.
- [ ] Pydantic validasyon hataları anlaşılır Türkçe mesajlarla dönmeli.

---

### 📋 Issue #5: LLM Kriter Bazlı Değerlendirme Motoru ("AI 4. Göz")
**Atanan:** `@Mehmet`  
**Etiketler:** `ai`, `llm`, `prompt-engineering`, `evaluation`, `priority:critical`

#### 🎯 Amaç:
TEKNOFEST şartnamesinde yer alan 5 ana değerlendirme kriterine göre (Özgünlük, Teknik Derinlik, Uygulanabilirlik, Sosyal/Ekonomik Etki, Sunum Kalitesi) raporu analiz edip hakeme ön puan ve gerekçeler sunan yapay zekâ değerlendiricisini kodlamak.

#### 🛠️ Nasıl Yapılacak (Teknik Adımlar):
1. `src/evaluation/rubric.py`: TEKNOFEST 0-100 puanlık rubric kriterlerini ve ağırlıklarını tanımlayın (Her kriter 0-20 puan).
2. `src/evaluation/evaluator.py`: OpenAI API (`gpt-4o` / `gpt-4o-mini` / `Claude 3.5 Sonnet` / Yerel Ollama) için structured JSON output üreten prompt şablonu geliştirin.
3. Few-shot örnekler ve Chain-of-Thought (CoT) akışı ile modelin gerekçesiz puan vermesini engelleyin.

#### ✅ Örnek Prompt ve Beklenen JSON Şeması:
```json
{
  "total_score": 78,
  "criteria": [
    {
      "name": "Özgünlük ve Yenilik",
      "score": 16,
      "max_score": 20,
      "reasoning": "Literatürdeki mevcut algoritmaları iyi birleştirmiş ancak donanım entegrasyonu standart.",
      "strengths": ["Hibrit yaklaşım özgün", "Alternatif çözümler kıyaslanmış"],
      "weaknesses": ["Piyasa benzerlerinden farkı yeterince vurgulanmamış"]
    },
    {
      "name": "Teknik Derinlik ve Yöntem",
      "score": 17,
      "max_score": 20,
      "reasoning": "Matematiksel modelleme ve algoritma adımları net, mimari şema detaylı.",
      "strengths": ["Metrikler somut verilmiş"],
      "weaknesses": ["Gecikme analizleri eksik"]
    }
  ]
}
```

---

### 📋 Issue #6: Dinamik Yarışmacı Gelişim Raporu ve Karne Üretici Modülü
**Atanan:** `@Mehmet`  
**Etiketler:** `ai`, `feedback`, `generator`, `priority:high`

#### 🎯 Amaç:
Yarışmacının elenmesi veya finale kalması fark etmeksizin; projesini geliştirebilmesi için güçlü yönlerini, eksiklerini ve bir sonraki aşama için atması gereken somut adımları içeren yapıcı bir karne üretmek.

#### 🛠️ Nasıl Yapılacak (Teknik Adımlar):
1. `src/feedback/generator.py` dosyasını oluşturun.
2. Checkers ve Evaluator modüllerinden gelen verileri birleştirerek yarışmacıya hitap eden, teşvik edici ve öğretici bir dille özet çıktı hazırlayın.
3. PDF/Markdown karne raporu indirme desteği sağlayın.

#### ✅ Kabul Kriterleri (Definition of Done):
- [ ] Hakaret veya demotive edici ifadeler sıfır olmalı, tamamen pedagojik ve teknik gelişim odaklı olmalı.
- [ ] En az 3 somut "Bir Sonraki Adım İçin Eylem Önerisi" içermeli.

---

## 🟣 EMRE İÇİN ISSUE'LAR (Frontend, UI/UX, Hakem & Yarışmacı Paneli)

### 📋 Issue #7: UI/UX Mimarisi, Tasarım Sistemi ve Genel Dashboard İskeleti
**Atanan:** `@Emre`  
**Etiketler:** `frontend`, `ui-ux`, `design-system`, `priority:high`

#### 🎯 Amaç:
Jüriyi ilk bakışta etkileyecek, koyu/açık modern temalı, glassmorphism efektli, modern tipografili (Inter/Outfit) ve hızlı tepki veren bir dashboard arayüzü inşa etmek.

#### 🎨 UI/UX Tasarım Standartları (Jüriyi Etkileyecek Kurallar):
1. **Renk Paleti:**
   * Birincil Vurgu: `#0066FF` (Teknolojik Mavi) & `#00D2FF` (Kuantum/AI Neon Mavisi)
   * Arka Plan (Dark): `#0B0F19` & Kartlar `#111827` (Hafif border ve shadow ile)
   * Durum Renkleri: Yeşil (`#10B981` - Uygun), Sarı (`#F59E0B` - Dikkat), Kırmızı (`#EF4444` - Hata/Yüksek Benzerlik)
2. **Düzen:** Sol sabit navbar (Roller ve Sayfalar), Üst Header (Yarışma seçici ve Bildirimler), Orta İçerik (Geniş veri kartları).
3. **Mikro-Animasyonlar:** Yükleme durumlarında zarif skeleton loader'lar, puanlama barlarında yumuşak dolma animasyonları.

---

### 📋 Issue #8: Hakem Karar Destek Paneli ("AI 4. Göz" Ekranı)
**Atanan:** `@Emre`  
**Etiketler:** `frontend`, `ui-ux`, `referee-view`, `priority:critical`

#### 🎯 Amaç:
Hakemin raporu okurken aynı ekranda yapay zekânın çıkardığı tüm ön kontrolleri, benzerlik alıntılarını ve kriter önerilerini görüp kendi nihai kararını kolayca verebileceği 2 kolonlu (Split View) panel geliştirmek.

#### 🖥️ Ekran Bileşenleri ve Yerleşim Mantığı:
* **Sol Kolon (PDF Görüntüleyici):** Yüklenen raporun sayfaları taranabilir ve işaretlenebilir olmalı.
* **Sağ Kolon (AI 4. Göz Paneli):**
  * *Hızlı Durum Rozetleri:* Dil: TR (✅), Şablon: %100 Uyumlu (✅), Başlıklar: 6/6 Tam (✅), Benzerlik: %12 (Düşük Risk 🟢).
  * *Kriter Puanlama Kartları:* Her kriter için AI öneri puanı, gerekçesi ve hakemin puanı değiştirebileceği interaktif slider/input.
  * *Hakem Notu & Onay Butonu:* "AI Önerisini Onayla" veya "Özelleştir ve Kaydet" butonu.

#### ✅ Kabul Kriterleri (Definition of Done):
- [ ] Hakem tüm AI analizlerini tek sayfada kaydırma yapmadan görebilmeli.
- [ ] Hakem puanları değiştirdiğinde anlık toplam puan otomatik hesaplanmalı.

---

### 📋 Issue #9: Yarışmacı Gelişim Karnesi ve Yönetici İzleme Ekranı
**Atanan:** `@Emre`  
**Etiketler:** `frontend`, `ui-ux`, `contestant-view`, `admin-view`, `priority:high`

#### 🎯 Amaç:
Yarışmacıların sonuçlarını gelişim odaklı grafiklerle inceleyebileceği sayfa ile yöneticilerin tüm yarışma istatistiklerini izleyeceği canlı ekranı kodlamak.

#### 🖥️ Ekran Bileşenleri:
1. **Yarışmacı Karnesi:**
   * Güçlü Yönler (Yeşil onay ikonlu kartlar)
   * Gelişime Açık Yönler (Turuncu uyarı ikonlu kartlar)
   * "Sonraki Aşamada Ne Yapmalısınız?" (Adım adım aksiyon rehberi)
   * PDF Olarak İndir Butonu
2. **Yönetici Dashboard (Admin/Yarışma Yöneticisi):**
   * Toplam Yüklenen Rapor Sayısı, İncelenen Rapor Sayısı, Bekleyenler
   * Ortalama Puan Dağılım Grafiği (Histogram / Bar Chart)
   * Kategori Dağılımı (Donut Chart)
   * "Yüksek Benzerlik Riski Taşıyan Projeler" Uyarı Listesi

---

# 🚀 GİT VE GİTHUB YÜKLEME ADIMLARI

Bu doküman hazırlandıktan sonra projeyi GitHub'a yüklemek için terminalde şu adımları uygulayın:

```powershell
# 1. Depoyu başlatın
git init

# 2. Tüm dosyaları ve dokümanları ekleyin
git add .

# 3. Anlamlı ilk commit mesajı
git commit -m "docs: Problem 4 gorev dagilimi, mimari analizi ve GitHub issue sablonlari hazirlandi"

# 4. Ana dalı ayarlayın
git branch -M main

# 5. Uzak GitHub reponuzu bağlayın
git remote add origin https://github.com/mehmetcelikcmyk/T-Sistem.git

# 6. GitHub'a push yapın
git push -u origin main
```
