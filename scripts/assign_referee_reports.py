"""
assign_referee_reports.py
=========================
1. usr_hakem_ef6def ve system_admin kullanicilarini auth_users tablosuna ekler.
2. Rapor havuzundaki ilk 15 raporu bu hakeme atar (report_assignments).
Boylece hakem ekraninda degerlendirilecek raporlar ve metrikler dolu gorunur.
"""
import sys
sys.path.insert(0, '.')
from src.data.client import get_client
from src.data import repos

client = get_client()

# 1. Kullanicilari auth_users'a ekle
client.execute("""
    INSERT OR IGNORE INTO auth_users (user_id, email, name, surname, role, status, created_at, updated_at)
    VALUES ('usr_hakem_ef6def', 'hakem@tsistem.org', 'Prof. Dr. Ahmet', 'Yılmaz (Hakem)', 'hakem', 'aktif', '2026-08-25T00:00:00Z', '2026-08-25T00:00:00Z')
""")

client.execute("""
    INSERT OR IGNORE INTO auth_users (user_id, email, name, surname, role, status, created_at, updated_at)
    VALUES ('system_admin', 'admin@tsistem.org', 'Sistem', 'Yöneticisi', 'admin', 'aktif', '2026-08-25T00:00:00Z', '2026-08-25T00:00:00Z')
""")

print("Kullanıcılar auth_users tablosuna eklendi.")

# 2. Raporlari ata
r = repos()
all_reps = r.reports.list_for_admin()
assigned_count = 0
for rep in all_reps[:15]:
    try:
        r.evaluations.assign(rep.report_id, 'usr_hakem_ef6def', assigned_by='system_admin')
        assigned_count += 1
    except Exception as e:
        print(f"Atama uyarisi ({rep.report_id}): {e}")

assigned = r.evaluations.list_for_referee('usr_hakem_ef6def')
print(f"=== BASARILI: Hakeme {len(assigned)} rapor atandi ===")
for a in assigned[:5]:
    print(f"  - [{a['stage_code']}] {a['file_name']} ({a['competition_name']})")
