import os
import requests
import json
import boto3

ACCOUNT_ID = 'fad19865339b3a1dc3e3de4901a451bf'
DB_ID = '158fadb7-cc38-4692-8c99-4400eefc8d52'
TOKEN = 'cfut_JTuvlaNx2MxlRZxgJ0HGPM5ZW8uCr2cokGc63t1wbf36def6'
D1_URL = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query'
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

def d1_query(sql):
    r = requests.post(D1_URL, headers=HEADERS, json={'sql': sql}, timeout=15)
    data = r.json()
    if not data.get('success'):
        print('D1 Hata:', data.get('errors'))
        return []
    return data['result'][0]['results']

print('=== 1. CLOUDFLARE D1 VERİTABANI KONTROLÜ ===')
try:
    tbls = d1_query("SELECT name FROM sqlite_master WHERE type='table'")
    print('D1 Tabloları:', [t['name'] for t in tbls])
    
    cols = d1_query("PRAGMA table_info(reports)")
    print('reports tablosu kolonları:', [c['name'] for c in cols])
    
    rep_count = d1_query("SELECT count(*) as c FROM reports")[0]['c']
    print(f"reports tablosundaki toplam rapor: {rep_count}")
    
    comp_count = d1_query("SELECT count(*) as c FROM competitions")[0]['c']
    print(f"competitions tablosundaki yarışma: {comp_count}")
    
    rub_count = d1_query("SELECT count(*) as c FROM competition_rubrics")[0]['c']
    print(f"competition_rubrics tablosundaki rubrik: {rub_count}")

    team_count = d1_query("SELECT count(*) as c FROM teams")[0]['c']
    print(f"teams tablosundaki takım: {team_count}")

    dist = d1_query("SELECT competition_id, count(*) as c FROM reports GROUP BY competition_id ORDER BY c DESC")
    print('\nCloudflare D1 Rapor Dağılımı:')
    for item in dist:
        print(f"  - {item.get('competition_id')}: {item.get('c')} rapor")

    sample_reports = d1_query("SELECT * FROM reports LIMIT 3")
    print('\nÖrnek D1 Rapor Kaydı:')
    if sample_reports:
        print(json.dumps(sample_reports[0], indent=2, ensure_ascii=False))

except Exception as e:
    print('D1 Hatası:', e)

print('\n=== 2. CLOUDFLARE R2 BULUT DEPOLAMA KONTROLÜ ===')
try:
    R2_ACCESS_KEY = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID', 'c1ff93630f9a2e666a2cbdb7ce8590c8')
    R2_SECRET_KEY = os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY', '4be7282b8a7863ea6bafe6a0b9aebeee2a106eeeb1d0db7fd598444a7e937d97')
    R2_BUCKET = os.environ.get('CLOUDFLARE_R2_BUCKET_NAME', 'tsistem-reports')
    R2_ENDPOINT = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"

    s3 = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto'
    )
    
    objs = s3.list_objects_v2(Bucket=R2_BUCKET, MaxKeys=1000)
    contents = objs.get('Contents', [])
    print(f"Cloudflare R2 Bucket ({R2_BUCKET}) içindeki toplam dosya: {len(contents)}")
    if contents:
        print('Örnek R2 Dosyaları (ilk 5):')
        for o in contents[:5]:
            print(f"  - {o['Key']} ({o['Size'] / 1024:.1f} KB)")
except Exception as e:
    print('R2 Hatası:', e)
