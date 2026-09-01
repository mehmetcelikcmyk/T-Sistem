"""
complete_r2_sync.py
===================
Cloudflare R2 (t-sistem-r2) bucket'ındaki eksik dosyaları kontrol edip tamamlar.
"""

import os
import boto3
import time

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
                    parts = rel_to_asam.replace('\\', '/').split('/')
                    
                    if 'sablon' in parts:
                        stage_code = parts[1] if len(parts) >= 4 else 'GENEL'
                        r2_key = f"yarismalar/{slug}/sablon/{stage_code}/{f}"
                        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if f.endswith('.docx') else 'application/pdf'
                        tasks.append((local_path, r2_key, content_type))
                    elif 'yarismaci_raporlari' in parts:
                        r2_key = f"yarismalar/{slug}/{rel_to_asam.replace('\\', '/')}"
                        tasks.append((local_path, r2_key, 'application/pdf'))
                        
    return tasks

def main():
    s3 = get_s3_client()
    paginator = s3.get_paginator('list_objects_v2')
    
    existing_keys = set()
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        for obj in page.get('Contents', []):
            existing_keys.add(obj['Key'])
            
    print(f"R2 uzerindeki mevcut nesne sayisi: {len(existing_keys)} adet", flush=True)
    
    tasks = collect_files_to_upload()
    missing = [t for t in tasks if t[1] not in existing_keys]
    print(f"Eksik kalan dosya sayisi: {len(missing)} adet", flush=True)
    
    for idx, (local_path, r2_key, content_type) in enumerate(missing, 1):
        success = False
        for attempt in range(4):
            try:
                with open(local_path, 'rb') as fp:
                    s3.put_object(
                        Bucket=BUCKET_NAME,
                        Key=r2_key,
                        Body=fp,
                        ContentType=content_type
                    )
                print(f"  [{idx:02d}/{len(missing)}] [OK] {r2_key}", flush=True)
                success = True
                break
            except Exception as e:
                print(f"  [{idx:02d}/{len(missing)}] [Tekrar Deneniyor {attempt+1}] {r2_key}: {e}", flush=True)
                time.sleep(2)
        if not success:
            print(f"  [HATA] {r2_key} yuklenemedi!", flush=True)

    # Final Dogrulama
    final_keys = set()
    total_size = 0
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        for obj in page.get('Contents', []):
            final_keys.add(obj['Key'])
            total_size += obj['Size']
            
    print("\n" + "="*70, flush=True)
    print("CLOUDFLARE R2 NIHAI SENKRONIZASYON RAPORU", flush=True)
    print(f"  * R2 Bucket Adi:          {BUCKET_NAME}", flush=True)
    print(f"  * Toplam Nesne (Objects): {len(final_keys)} adet", flush=True)
    print(f"  * Toplam Boyut (Size):    {total_size / (1024*1024):.2f} MB", flush=True)
    print("="*70, flush=True)

if __name__ == '__main__':
    main()
