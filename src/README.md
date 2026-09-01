# 💻 Src (Kaynak Kod) Klasörü — Problem 4 Modülleri

Bu klasör, **TEKNOFEST Yapay Zekâ Destekli Değerlendirme Sistemi**'nin (Problem 4) uçtan uca çalışan üretim kodlarını barındırır.

---

## 📁 Modül Mimarisi

```
src/
├── ingestion/              # PDF rapor yükleme, metin ve tablo ayrıştırma (PyMuPDF / pdfplumber)
│   ├── pdf_loader.py       # PDF dosyalarını okur ve ham metinleri çıkarır
│   └── preprocessor.py     # Metin temizleme, formatlama ve LangChain chunking
│
├── checkers/               # Statik ve kural tabanlı doğrulama modülleri
│   ├── language_checker.py # Rapor dilinin otomatik tespiti (Türkçe/İngilizce)
│   ├── template_checker.py # Font, sayfa yapısı, şablon uygunluk kontrolü
│   ├── section_checker.py  # Zorunlu başlıkların varlığı ve içerik doluluk kontrolü
│   └── category_checker.py # Rapor konusu ile yarışma kategorisi anlamsal uyum kontrolü
│
├── similarity/             # Semantik benzerlik ve intihal tespit motoru
│   ├── embeddings.py       # Metin embedding vektör üretimi (OpenAI / HuggingFace)
│   └── vector_store.py     # FAISS / ChromaDB vektör araması ve kosinüs benzerlik tespiti
│
├── evaluation/             # Kriter bazlı yapay zekâ değerlendirme ("AI 4. Göz")
│   ├── rubric.py           # TEKNOFEST puanlama kriterleri (Özgünlük, Teknik, Etki vb.)
│   └── evaluator.py        # LLM tabanlı kriter analizi, gerekçelendirme ve ön puanlama
│
├── feedback/               # Yarışmacı gelişim ve karne motoru
│   └── generator.py        # Güçlü yönler, gelişim alanları ve yapıcı geri bildirim çıktısı
│
├── api/                    # Web servis ve REST API katmanı
│   ├── routes.py           # FastAPI endpoint'leri (Yönetici, Hakem, Yarışmacı)
│   └── schemas.py          # Pydantic veri modelleri ve request/response şemaları
│
└── main.py                 # Uygulamayı başlatan ana giriş noktası
```

---

## 🎯 MVP 6 Zorunlu Maddenin Kod Eşleşmesi

| MVP Gereksinimi | İlgili Kod Modülü | Fonksiyon / Sorumluluk |
| :--- | :--- | :--- |
| **1. Dil & Şablon Kontrolü** | `src/checkers/language_checker.py`<br>`src/checkers/template_checker.py` | Dil tespiti, sayfa marjinleri, font ailesi/boyutu ve şablon uyumu |
| **2. Başlık & İçerik Kontrolü** | `src/checkers/section_checker.py` | Zorunlu ana/alt başlık tespiti ve bölümlerin doluluk doğrulaması |
| **3. Kategori Uygunluğu** | `src/checkers/category_checker.py` | Rapor konusu ile yarışma kategori tanımının anlamsal eşleşmesi |
| **4. Benzerlik Analizi** | `src/similarity/vector_store.py` | Başvurular arası semantik embedding & intihal eşik taraması |
| **5. AI Kriter Değerlendirmesi** | `src/evaluation/evaluator.py` | Rubric bazlı hakem karar destek ön puanlama & gerekçelendirme |
| **6. Geri Bildirim Üretimi** | `src/feedback/generator.py` | Yarışmacıya projesinin güçlü ve gelişime açık yönlerini üretme |

---

## ⚠️ Geliştirme Kuralları
1. **Modülerlik:** Tüm fonksiyonlar `typing` (tip ipuçları) ve docstring içermelidir.
2. **Hata Yönetimi:** PDF bozuklukları, API kesintileri ve eksik veri durumları için `try-except` ve fallback mekanizmaları kullanılmalıdır.
3. **Konfigürasyon:** Sabit değerler doğrudan koda gömülmemeli, `.env` veya `config.py` üzerinden yönetilmelidir.