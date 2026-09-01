# T-Sistem — Arayüz ↔ Backend Sözleşmesi (v1)

Arayüz backend'in *iç yapısını* bilmez. Yalnızca aşağıdaki endpoint'lere ve
`analiz_sonucu.schema.json` şemasına güvenir. Bu sözleşme dondurulduktan sonra
arayüz ve backend birbirini beklemeden paralel geliştirilebilir.

## Endpoint'ler

| Metot | Yol | Döner | Kim kullanır |
|---|---|---|---|
| `GET` | `/api/yarismalar` | `[{yarisma_id, ad, kategori_sayisi, rapor_sayisi}]` | Yarışma Yöneticisi, Dashboard |
| `POST` | `/api/yarismalar/{id}/raporlar` | `{kuyruk_id, alinan: int}` | Yarışma Yöneticisi (toplu yükleme) |
| `GET` | `/api/yarismalar/{id}/raporlar` | `[analiz_sonucu]` (özet alanlar yeterli) | Hakem listesi, Dashboard |
| `GET` | `/api/raporlar/{rapor_id}/analiz` | `analiz_sonucu` (tam) | Hakem ekranı, Yarışmacı karnesi |
| `POST` | `/api/raporlar/{rapor_id}/hakem-karari` | `{ok: true}` | Hakem onayı |
| `GET` | `/api/yarismalar/{id}/metrikler` | `{toplam, tamamlanan, bekleyen, hatali, ortalama_puan, kriter_ortalamalari, gunluk_hacim, benzerlik_uyarilari}` | Dashboard |

## Kurallar

1. **Şema dondu.** Alan adı değişikliği üç kişinin onayıyla olur; tek taraflı değişiklik yasak.
2. **Boş veri hata değildir.** `benzerlik: []` = uyarı yok. Arayüz bunu "uyarı bulunmadı" olarak gösterir.
3. **Kısmi sonuç serbest.** `durum: "kuyrukta"` ise `kriterler` boş gelebilir; arayüz iskelet (skeleton) gösterir.
4. **Puan aralığı 0–5**, ağırlıklar yüzde olarak gelir ve toplamı 100 olmalıdır.
5. **`kaynak_alinti` zorunludur.** Kanıtsız puan arayüzde "kanıt yok" uyarısıyla işaretlenir — bu, motorun eksik olduğunu görünür kılar.

## Arayüzü gerçek backend'e bağlama

Arayüz varsayılan olarak mock veriyle çalışır. Backend hazır olduğunda tek
değişiklik:

```bash
export T_SISTEM_API="http://localhost:8000"
streamlit run src/ui/app.py
```

`api_client.py` bu değişkeni görürse HTTP'ye, görmezse mock veriye gider.
Arayüz kodunda başka hiçbir satır değişmez.
