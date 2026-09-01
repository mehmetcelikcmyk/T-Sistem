"""
seed_participant_reports_to_d1.py
==================================
Cloudflare R2'ye yüklenmiş olan 139 yarışmacı raporunu
Cloudflare D1 (reports, teams, applications) tablolarına kaydeder.
Böylece hakem ve yönetici panellerinde bu raporlar test/değerlendirme için hazır görünür.
"""

import os
import re
import uuid
import requests
from datetime import datetime, timezone
import boto3

ACCOUNT_ID = 'fad19865339b3a1dc3e3de4901a451bf'
DB_ID = '158fadb7-cc38-4692-8c99-4400eefc8d52'
TOKEN = 'cfut_JTuvlaNx2MxlRZxgJ0HGPM5ZW8uCr2cokGc63t1wbf36def6'
D1_URL = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query'
HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

DATA_DIR = r'c:\Users\mehme\OneDrive\Desktop\T-Sistem\data\yarismalar'

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def new_id() -> str:
    return str(uuid.uuid4())

def sql_quote(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return f"'{s}'"

def d1_exec_batch(sql_statements: list[str]):
    if not sql_statements:
        return
    full_script = ";\n".join(sql_statements) + ";"
    resp = requests.post(D1_URL, headers=HEADERS, json={'sql': full_script}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"D1 API Error ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    if not data.get('success'):
        raise RuntimeError(f"D1 Query Error: {data.get('errors')}")
    return data

def main():
    print("--- 139 Yarismaci Raporu D1 Veritabanina Kaydediliyor ---", flush=True)
    
    reports_to_seed = []
    
    for slug in sorted(os.listdir(DATA_DIR)):
        comp_dir = os.path.join(DATA_DIR, slug)
        if not os.path.isdir(comp_dir):
            continue
        asam_dir = os.path.join(comp_dir, 'asamalar')
        if not os.path.exists(asam_dir):
            continue
            
        for root, dirs, files in os.walk(asam_dir):
            for f in files:
                if f.endswith('.pdf') and 'yarismaci_raporlari' in root:
                    local_path = os.path.join(root, f)
                    rel = os.path.relpath(local_path, comp_dir).replace('\\', '/')
                    r2_key = f"yarismalar/{slug}/{rel}"
                    
                    # Parse stage_code and level from path
                    # e.g. "asamalar/ODR/seviye/universite_ve_uzeri/yarismaci_raporlari/xxx.pdf"
                    # e.g. "asamalar/KTR/yarismaci_raporlari/xxx.pdf"
                    parts = rel.split('/')
                    stage_code = 'GENEL'
                    level = 'Genel'
                    branch = None
                    
                    if len(parts) >= 2:
                        stage_code = parts[1]
                    if 'seviye' in parts:
                        s_idx = parts.index('seviye')
                        if s_idx + 1 < len(parts):
                            level = parts[s_idx + 1].replace('_', ' ').title()
                    elif 'kategoriler' in parts:
                        k_idx = parts.index('kategoriler')
                        if k_idx + 1 < len(parts):
                            branch = parts[k_idx + 1]
                            
                    reports_to_seed.append({
                        'slug': slug,
                        'stage_code': stage_code.upper(),
                        'level': level,
                        'branch': branch,
                        'file_name': f,
                        'r2_key': r2_key,
                        'size': os.path.getsize(local_path)
                    })
                    
    print(f"Toplam tespit edilen rapor: {len(reports_to_seed)} adet", flush=True)
    
    d1_stmts = []
    
    # Ensure seed user exists
    d1_stmts.append(f"""
        INSERT OR IGNORE INTO auth_users (
            user_id, email, name, surname, role, status, created_at, updated_at
        ) VALUES (
            'seed_user', 'yarismaci@teknofest.org', 'Yarışmacı', 'Kullanıcı', 'yarismaci', 'aktif',
            {sql_quote(now_iso())}, {sql_quote(now_iso())}
        )
    """)

    # Clean existing mock reports
    d1_stmts.append("DELETE FROM reports WHERE uploaded_by = 'system_seed'")
    d1_stmts.append("DELETE FROM applications WHERE team_id LIKE 'team_seed_%'")
    d1_stmts.append("DELETE FROM teams WHERE team_id LIKE 'team_seed_%'")
    
    for idx, rep in enumerate(reports_to_seed, 1):
        team_id = f"team_seed_{idx:03d}"
        team_code = f"TAKIM-{idx:03d}"
        team_name = f"Yarışmacı Takım {idx:03d}"
        app_id = f"app_seed_{idx:03d}"
        report_id = f"rep_seed_{idx:03d}"
        
        # 1. Team
        d1_stmts.append(f"""
            INSERT OR REPLACE INTO teams (
                team_id, team_code, name, level, institution, captain_user_id, status, created_at, updated_at
            ) VALUES (
                {sql_quote(team_id)}, {sql_quote(team_code)}, {sql_quote(team_name)}, {sql_quote(rep['level'])},
                'TEKNOFEST', 'seed_user', 'aktif', {sql_quote(now_iso())}, {sql_quote(now_iso())}
            )
        """)
        
        # 2. Application
        d1_stmts.append(f"""
            INSERT OR REPLACE INTO applications (
                app_id, team_id, competition_id, branch_code, level, status, created_at, updated_at
            ) VALUES (
                {sql_quote(app_id)}, {sql_quote(team_id)}, {sql_quote(rep['slug'])},
                {sql_quote(rep['branch'])}, {sql_quote(rep['level'])}, 'aktif',
                {sql_quote(now_iso())}, {sql_quote(now_iso())}
            )
        """)
        
        # 3. Report
        d1_stmts.append(f"""
            INSERT OR REPLACE INTO reports (
                report_id, app_id, competition_id, stage_code, level, branch_code,
                version, file_name, r2_key, page_count, status, uploaded_by, created_at, updated_at
            ) VALUES (
                {sql_quote(report_id)}, {sql_quote(app_id)}, {sql_quote(rep['slug'])},
                {sql_quote(rep['stage_code'])}, {sql_quote(rep['level'])}, {sql_quote(rep['branch'])},
                1, {sql_quote(rep['file_name'])}, {sql_quote(rep['r2_key'])}, 15,
                'BEKLEMEDE', 'system_seed', {sql_quote(now_iso())}, {sql_quote(now_iso())}
            )
        """)
        
    # Execute batch in D1
    chunk_size = 60
    for c_i in range(0, len(d1_stmts), chunk_size):
        chunk = d1_stmts[c_i:c_i+chunk_size]
        d1_exec_batch(chunk)
        
    print("\n" + "="*70, flush=True)
    print("139 YARISMACI RAPORU D1 VERITABANINA EKSIKSIZ ISLENDI!", flush=True)
    print(f"  * Eklenen Rapor Satiri:     {len(reports_to_seed)} adet", flush=True)
    print(f"  * Olusturulan Basvuru/Takim: {len(reports_to_seed)} adet", flush=True)
    print("="*70, flush=True)

if __name__ == '__main__':
    main()
