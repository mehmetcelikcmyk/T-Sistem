"""
upload_all_to_r2.py
===================
T-Sistem'deki tüm logoları, şartnameleri, aşama şablonlarını ve yarışmacı raporlarını
Cloudflare R2 (t-sistem-r2) bucket'ına paralel ve yüksek hızda yükler.
"""

import os
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed

ENDPOINT_URL = 'https://fad19865339b3a1dc3e3de4901a451bf.r2.cloudflarestorage.com'
ACCESS_KEY = 'de3e3ec4081af07c4b59b3ea89a10bb1'
SECRET_KEY = '80480c9d2132f21c7a5670b992e35724f20b264bb4be3ed2bf33a1e2afd42e66'
BUCKET_NAME = 't-sistem-r2'

DATA_DIR = r'c:\Users\mehme\OneDrive\Desktop\T-Sistem\data'
YARISMALAR_DIR = os.path.join(DATA_DIR, 'yarismalar')

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name='auto'
    )

def collect_files_to_upload():
    tasks = []
    
    for slug in sorted(os.listdir(YARISMALAR_DIR)):
        comp_dir = os.path.join(YARISMALAR_DIR, slug)
        if not os.path.isdir(comp_dir):
            continue
            
        # 1. Logos
        for f in os.listdir(comp_dir):
            if 'logo' in f.lower() and os.path.isfile(os.path.join(comp_dir, f)):
                ext = os.path.splitext(f)[1]
                local_path = os.path.join(comp_dir, f)
                r2_key = f"yarismalar/{slug}/logo.png"
                tasks.append((local_path, r2_key, 'image/png'))
                if ext.lower() != '.png':
                    # also upload with original name
                    tasks.append((local_path, f"yarismalar/{slug}/{f}", 'image/jpeg' if 'jp' in ext else 'image/webp'))
                    
        # 2. Sartnameler
        sart_dir = os.path.join(comp_dir, 'sartname')
        if os.path.exists(sart_dir):
            for f in os.listdir(sart_dir):
                local_path = os.path.join(sart_dir, f)
                if os.path.isfile(local_path):
                    r2_key = f"yarismalar/{slug}/sartname/{f}"
                    content_type = 'application/pdf' if f.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    tasks.append((local_path, r2_key, content_type))
                    
        # 3. Asamalar (Sablonlar & Yarismaci Raporlari)
        asam_dir = os.path.join(comp_dir, 'asamalar')
        if os.path.exists(asam_dir):
            for root, dirs, files in os.walk(asam_dir):
                for f in files:
                    local_path = os.path.join(root, f)
                    rel_to_asam = os.path.relpath(local_path, comp_dir)
                    # rel_to_asam: e.g. "asamalar\KTR\sablon\dosya.docx"
                    parts = rel_to_asam.replace('\\', '/').split('/')
                    
                    if 'sablon' in parts:
                        # Find stage_code
                        # parts: ['asamalar', 'KTR', 'sablon', 'dosya.docx']
                        stage_code = parts[1] if len(parts) >= 4 else 'GENEL'
                        r2_key = f"yarismalar/{slug}/sablon/{stage_code}/{f}"
                        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if f.endswith('.docx') else 'application/pdf'
                        tasks.append((local_path, r2_key, content_type))
                    elif 'yarismaci_raporlari' in parts:
                        # r2_key: yarismalar/{slug}/asamalar/.../yarismaci_raporlari/{f}
                        r2_key = f"yarismalar/{slug}/{rel_to_asam.replace('\\', '/')}"
                        tasks.append((local_path, r2_key, 'application/pdf'))
                        
    return tasks

def upload_single_file(task):
    local_path, r2_key, content_type = task
    s3 = get_s3_client()
    try:
        with open(local_path, 'rb') as fp:
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=r2_key,
                Body=fp,
                ContentType=content_type
            )
        return True, r2_key, os.path.getsize(local_path)
    except Exception as e:
        return False, r2_key, str(e)

def main():
    print("--- Cloudflare R2 Dosya Senkronizasyonu Baslatiliyor ---", flush=True)
    tasks = collect_files_to_upload()
    print(f"Yuklenecek toplam dosya adedi: {len(tasks)}", flush=True)
    
    total_size = sum([os.path.getsize(t[0]) for t in tasks])
    print(f"Toplam dosya boyutu: {total_size / (1024*1024):.2f} MB", flush=True)
    
    success_count = 0
    fail_count = 0
    uploaded_bytes = 0
    
    # 15 es zamanli is parcacigi ile paralel yukleme
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(upload_single_file, t): t for t in tasks}
        
        for i, future in enumerate(as_completed(futures), 1):
            success, key, info = future.result()
            if success:
                success_count += 1
                uploaded_bytes += info
                if i % 10 == 0 or i == len(tasks):
                    print(f"  [{i:03d}/{len(tasks)}] [OK] {key} ({info/1024:.1f} KB)", flush=True)
            else:
                fail_count += 1
                print(f"  [{i:03d}/{len(tasks)}] [FAIL] {key}: {info}", flush=True)
                
    print("\n" + "="*70, flush=True)
    print("CLOUDFLARE R2 YUKLEME ISLEMI TAMAMLANDI!", flush=True)
    print(f"  * Basarili Yuklenen: {success_count} dosya", flush=True)
    print(f"  * Basarisiz:         {fail_count} dosya", flush=True)
    print(f"  * Toplam Boyut:      {uploaded_bytes / (1024*1024):.2f} MB", flush=True)
    print("="*70, flush=True)

if __name__ == '__main__':
    main()
