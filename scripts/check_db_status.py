"""Veritabanı durum doğrulama ve raporlama scripti."""
import sqlite3

conn = sqlite3.connect('data/tsistem.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

c_req = c.execute('SELECT count(*) FROM category_requirements').fetchone()[0]
r_req = c.execute('SELECT count(*) FROM report_template_requirements').fetchone()[0]
reps = c.execute('SELECT count(*) FROM reports').fetchone()[0]
ref_reps = c.execute("SELECT count(*) FROM reports WHERE referee_id IS NOT NULL AND referee_id != ''").fetchone()[0]

print("=" * 60)
print("VERİTABANI DOĞRULAMA RAPORU (TEMİZ & AYRI TABLOLAR)")
print("=" * 60)
print(f"1. Kategori Şartnameleri Tablosu (category_requirements)        : {c_req} Adet")
print(f"2. Aşama Rapor Şablonları Tablosu (report_template_requirements): {r_req} Adet")
print(f"3. Yarışmacı Başvuru Raporları Tablosu (reports)                : {reps} Adet")
print(f"4. Hakeme Atanmış Rapor Sayısı                                  : {ref_reps} Adet")

print("\nHakem Havuzundaki Raporların Kategori Dağılımı:")
for r in c.execute("SELECT category, count(*) as cnt FROM reports WHERE referee_id IS NOT NULL AND referee_id != '' GROUP BY category ORDER BY cnt DESC").fetchall():
    print(f"  - {r['category']}: {r['cnt']} Rapor")

print("\nRaporların Aşama Dağılımı:")
for r in c.execute("SELECT stage, count(*) as cnt FROM reports GROUP BY stage ORDER BY cnt DESC").fetchall():
    print(f"  - {r['stage']}: {r['cnt']} Rapor")

# Örnek kategori şartnamesi kaydı göster
sample_cat = c.execute("SELECT * FROM category_requirements LIMIT 1").fetchone()
if sample_cat:
    print(f"\nÖrnek Şartname Kaydı ({sample_cat['category_slug']}):")
    print(f"  Hedef Seviye: {sample_cat['target_level']}")
    print(f"  Takım Boyutu: {sample_cat['min_team_size']} - {sample_cat['max_team_size']} Kişi")
    print(f"  Danışman    : {sample_cat['advisor_required']}")

# Örnek şablon kaydı göster
sample_tpl = c.execute("SELECT * FROM report_template_requirements LIMIT 1").fetchone()
if sample_tpl:
    print(f"\nÖrnek Şablon Kaydı ({sample_tpl['template_id']}):")
    print(f"  Aşama      : {sample_tpl['stage_code']}")
    print(f"  Maks Sayfa : {sample_tpl['max_pages']}")
    print(f"  Ceza Kuralı: {sample_tpl['page_penalty_rule']}")

conn.close()
