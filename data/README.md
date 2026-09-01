# 📊 Data (Veri) Klasörü — Problem 4 Veri Mimarisi

Bu klasör, **TEKNOFEST Rapor Değerlendirme Sistemi** kapsamında kullanılan rapor PDF'lerini, şablon belgelerini, ayrıştırılmış metinleri ve vektör indekslerini barındırır.

---

## 📁 Klasör Hiyerarşisi

```
data/
├── raw/                       # Ham ve dokunulmamış yarışma verileri
│   ├── templates/             # Resmi güncel TEKNOFEST rapor şablonları (.pdf / .docx)
│   ├── sample_reports/        # Test ve değerlendirme için örnek yarışmacı raporları (.pdf)
│   └── criteria/              # Yarışma şartnameleri ve değerlendirme rubric kılavuzları
│
└── processed/                 # İşlenmiş ve modele hazır hale getirilmiş veriler
    ├── parsed_texts/          # PDF'lerden ayıklanmış temiz metinler (.json / .txt)
    ├── structured_sections/   # Başlıklarına göre parçalanmış JSON dokümanları
    └── vector_index/          # FAISS / ChromaDB vektör embedding indeks dosyaları
```

---

## 🔒 Veri Güvenliği ve Gizlilik
* **Kişisel Verilerin Korunması (KVKK):** Başvuru raporlarındaki isim, telefon, e-posta gibi kişisel veriler ön işleme aşamasında anonimleştirilmelidir.
* **Büyük Dosya Yönetimi:** 50 MB üzeri ham veri kümeleri ve vektör indeks dosyaları doğrudan GitHub'a yüklenmemelidir. Bunlar `.gitignore` dosyasında hariç tutulmalıdır.
* **Veri Kaydı:** Eklenen her yeni test kümesi veya şablon için `data/raw/dataset_manifest.json` dosyasına sürüm notu düşülmelidir.
