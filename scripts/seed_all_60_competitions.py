"""
seed_all_60_competitions.py
===========================
60 Yarışmanın tamamını:
1) D1 Veritabanı Şeması (yarismalar, yarisma_sartnameleri, yarisma_asamalari, rubrik_kriterleri, gerekli_bolumler)
2) T-Sistem Uygulama Şeması (competitions, competition_specs, competition_stages, stage_rubric_criteria)

hem Cloudflare D1'e hem yerel SQLite (data/tsistem.db) veritabanına yüksek performansla (batch modunda) aktarır.
"""

import os
import json
import glob
import sqlite3
import requests
import uuid
from datetime import datetime, timezone

ACCOUNT_ID = 'fad19865339b3a1dc3e3de4901a451bf'
DB_ID = '158fadb7-cc38-4692-8c99-4400eefc8d52'
TOKEN = 'cfut_JTuvlaNx2MxlRZxgJ0HGPM5ZW8uCr2cokGc63t1wbf36def6'
D1_URL = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query'
HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

DATA_DIR = r'c:\Users\mehme\OneDrive\Desktop\T-Sistem\data'
AI_JSON_DIR = os.path.join(DATA_DIR, 'ai_rapor_analizi')
SQLITE_DB_PATH = os.path.join(DATA_DIR, 'tsistem.db')


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


def is_regex_str(val: str) -> bool:
    if not isinstance(val, str):
        return False
    return val.startswith("(?i)") or "|" in val or "^" in val or ".*" in val


def extract_stages_list(stages_data) -> list[dict]:
    flat_stages = []
    if isinstance(stages_data, list):
        for s in stages_data:
            if isinstance(s, dict):
                flat_stages.append(s)
    elif isinstance(stages_data, dict):
        for sub_key, sub_list in stages_data.items():
            if isinstance(sub_list, list):
                for s in sub_list:
                    if isinstance(s, dict):
                        s_copy = dict(s)
                        s_copy['kategori_alani'] = sub_key
                        # If stage code exists, qualify it if needed or store sub_key
                        orig_code = s_copy.get('stage', 'GENEL')
                        s_copy['stage_code_qualified'] = f"{orig_code}_{sub_key}"
                        flat_stages.append(s_copy)
    return flat_stages


PDF_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS yarismalar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    kategori_adi TEXT,
    hedef_egitim_seviyesi TEXT,
    takim_uye_min INTEGER DEFAULT 1,
    takim_uye_max INTEGER DEFAULT 5,
    danisman_sarti TEXT,
    dil_gereksinimi TEXT DEFAULT 'Türkçe',
    yurutucu_kurum TEXT,
    etkinlik_yeri TEXT,
    keywords_json TEXT,
    oncelikli_gorevler_json TEXT,
    sartname_kisitlari_json TEXT,
    ozel_alanlar_json TEXT,
    logo_r2_key TEXT,
    aktif INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS yarisma_sartnameleri (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yarisma_id INTEGER NOT NULL REFERENCES yarismalar(id) ON DELETE CASCADE,
    dosya_adi TEXT NOT NULL,
    r2_key TEXT NOT NULL,
    dosya_tipi TEXT NOT NULL,
    sira INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS yarisma_asamalari (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yarisma_id INTEGER NOT NULL REFERENCES yarismalar(id) ON DELETE CASCADE,
    stage_kodu TEXT NOT NULL,
    sablon_adi TEXT,
    rubrik_aciklamasi TEXT,
    min_sayfa INTEGER,
    max_sayfa INTEGER,
    toplam_puan REAL,
    ozel_alanlar_json TEXT,
    sira INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rubrik_kriterleri (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asama_id INTEGER NOT NULL REFERENCES yarisma_asamalari(id) ON DELETE CASCADE,
    kriter_id_text TEXT NOT NULL,
    kriter_adi TEXT NOT NULL,
    max_puan REAL,
    aciklama TEXT,
    is_mandatory INTEGER DEFAULT 0,
    yonlendirici_sorular_json TEXT,
    sira INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gerekli_bolumler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asama_id INTEGER NOT NULL REFERENCES yarisma_asamalari(id) ON DELETE CASCADE,
    bolum_anahtari TEXT NOT NULL,
    bolum_degeri TEXT NOT NULL,
    is_regex INTEGER DEFAULT 0,
    sira INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_yarismalar_slug ON yarismalar(slug);
CREATE INDEX IF NOT EXISTS idx_asamalar_yarisma ON yarisma_asamalari(yarisma_id, stage_kodu);
CREATE INDEX IF NOT EXISTS idx_kriterler_asama ON rubrik_kriterleri(asama_id);
CREATE INDEX IF NOT EXISTS idx_bolumler_asama ON gerekli_bolumler(asama_id);
"""


def init_database_tables():
    print("--- 1. Tablolar Olusturuluyor ---", flush=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()
    cur.executescript(PDF_SCHEMA_SQL)
    conn.commit()
    conn.close()
    print("  [SQLite] Tablolar hazir.", flush=True)

    stmts = [s.strip() for s in PDF_SCHEMA_SQL.split(';') if s.strip()]
    d1_exec_batch(stmts)
    print("  [Cloudflare D1] Tablolar hazir.", flush=True)


def import_competitions():
    print("\n--- 2. 60 Yarisma Verisi Aktariliyor (Batch Modu) ---", flush=True)
    
    json_files = sorted(glob.glob(os.path.join(AI_JSON_DIR, '*.json')))
    print(f"Toplam JSON dosyasi: {len(json_files)}", flush=True)

    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()

    success_count = 0
    total_specs_count = 0
    total_stages_count = 0
    total_criteria_count = 0
    total_sections_count = 0

    for idx, jf in enumerate(json_files, 1):
        fname = os.path.basename(jf)
        with open(jf, 'r', encoding='utf-8') as fp:
            data = json.load(fp)

        slug = data.get('slug', fname.replace('.json', ''))
        name = data.get('name', slug)
        ai_rules = data.get('ai_rules', {})
        specifications = data.get('specifications', [])
        raw_stages = data.get('stages', [])
        stages = extract_stages_list(raw_stages)

        kategori_adi = ai_rules.get('kategori_adi', name)
        hedef_egitim_seviyesi = ai_rules.get('hedef_egitim_seviyesi', '')
        
        takim_kurallari = ai_rules.get('takim_kurallari', {})
        takim_uye = ai_rules.get('takim_uye_sayisi', {})
        if isinstance(takim_kurallari, dict):
            min_u = takim_kurallari.get('uye_sayisi_min', takim_uye.get('min', 1))
            max_u = takim_kurallari.get('uye_sayisi_max', takim_uye.get('max', 5))
        else:
            min_u = takim_uye.get('min', 1)
            max_u = takim_uye.get('max', 5)

        danisman_kurallari = ai_rules.get('danisman_kurallari', {})
        danisman_sarti = ai_rules.get('danisman_sarti')
        if not danisman_sarti and isinstance(danisman_kurallari, dict):
            danisman_sarti = danisman_kurallari.get('genel_kural', 'Istege bagli')

        dil = ai_rules.get('dil_gereksinimi', 'Türkçe')
        yurutucu = ai_rules.get('yurutucu_kurum')
        etkinlik_yeri = ai_rules.get('etkinlik_yeri')
        keywords = ai_rules.get('keywords', [])
        oncelikli_gorevler = ai_rules.get('oncelikli_gorevler', [])
        sartname_kisitlari = ai_rules.get('sartname_kisitlari_ve_yasaklar', [])

        standart_keys = {
            'kategori_slug', 'kategori_adi', 'hedef_egitim_seviyesi', 'takim_uye_sayisi',
            'danisman_sarti', 'keywords', 'oncelikli_gorevler', 'sartname_kisitlari_ve_yasaklar'
        }
        ozel_alanlar = {k: v for k, v in ai_rules.items() if k not in standart_keys}
        if 'mission_scoring' in data:
            ozel_alanlar['mission_scoring'] = data['mission_scoring']

        logo_r2 = f"yarismalar/{slug}/logo.png"

        # ── 1. SQLite Islemleri ──────────────────────────────────────────────
        cur.execute("""
            INSERT INTO yarismalar (
                slug, name, kategori_adi, hedef_egitim_seviyesi,
                takim_uye_min, takim_uye_max, danisman_sarti, dil_gereksinimi,
                yurutucu_kurum, etkinlik_yeri, keywords_json, oncelikli_gorevler_json,
                sartname_kisitlari_json, ozel_alanlar_json, logo_r2_key, aktif
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                kategori_adi=excluded.kategori_adi,
                hedef_egitim_seviyesi=excluded.hedef_egitim_seviyesi,
                takim_uye_min=excluded.takim_uye_min,
                takim_uye_max=excluded.takim_uye_max,
                danisman_sarti=excluded.danisman_sarti,
                dil_gereksinimi=excluded.dil_gereksinimi,
                yurutucu_kurum=excluded.yurutucu_kurum,
                etkinlik_yeri=excluded.etkinlik_yeri,
                keywords_json=excluded.keywords_json,
                oncelikli_gorevler_json=excluded.oncelikli_gorevler_json,
                sartname_kisitlari_json=excluded.sartname_kisitlari_json,
                ozel_alanlar_json=excluded.ozel_alanlar_json,
                updated_at=CURRENT_TIMESTAMP
        """, [
            slug, name, kategori_adi, hedef_egitim_seviyesi,
            min_u, max_u, str(danisman_sarti) if danisman_sarti else None, str(dil),
            yurutucu, etkinlik_yeri,
            json.dumps(keywords, ensure_ascii=False),
            json.dumps(oncelikli_gorevler, ensure_ascii=False),
            json.dumps(sartname_kisitlari, ensure_ascii=False),
            json.dumps(ozel_alanlar, ensure_ascii=False) if ozel_alanlar else None,
            logo_r2
        ])
        yarisma_id_sq = cur.execute("SELECT id FROM yarismalar WHERE slug = ?", [slug]).fetchone()[0]

        # Sartnameler SQLite
        cur.execute("DELETE FROM yarisma_sartnameleri WHERE yarisma_id = ?", [yarisma_id_sq])
        for s_idx, dosya in enumerate(specifications):
            ext = dosya.split('.')[-1].upper()
            r2_spec = f"yarismalar/{slug}/sartname/{dosya}"
            cur.execute("""
                INSERT INTO yarisma_sartnameleri (yarisma_id, dosya_adi, r2_key, dosya_tipi, sira)
                VALUES (?, ?, ?, ?, ?)
            """, [yarisma_id_sq, dosya, r2_spec, ext, s_idx])
            total_specs_count += 1

        # Asamalar SQLite
        old_asamalar_sq = [r[0] for r in cur.execute("SELECT id FROM yarisma_asamalari WHERE yarisma_id = ?", [yarisma_id_sq]).fetchall()]
        for aid in old_asamalar_sq:
            cur.execute("DELETE FROM rubrik_kriterleri WHERE asama_id = ?", [aid])
            cur.execute("DELETE FROM gerekli_bolumler WHERE asama_id = ?", [aid])
        cur.execute("DELETE FROM yarisma_asamalari WHERE yarisma_id = ?", [yarisma_id_sq])

        for st_idx, st in enumerate(stages):
            st_kodu = st.get('stage_code_qualified', st.get('stage', 'GENEL'))
            sablon = st.get('template')
            rubric = st.get('rubric', {})
            rubrik_aciklamasi = rubric.get('description')
            min_s = rubric.get('min_pages')
            max_s = rubric.get('max_pages')
            if max_s == 0:
                max_s = None

            criteria = rubric.get('criteria', [])
            req_sections = rubric.get('required_sections', {})

            calc_total = sum([c.get('max_score', 0) for c in criteria if isinstance(c.get('max_score'), (int, float))])
            if calc_total == 0 and any(c.get('max_score') is None for c in criteria):
                calc_total = None

            asama_ozel = {k: v for k, v in st.items() if k not in ('stage', 'template', 'rubric')}

            cur.execute("""
                INSERT INTO yarisma_asamalari (
                    yarisma_id, stage_kodu, sablon_adi, rubrik_aciklamasi,
                    min_sayfa, max_sayfa, toplam_puan, ozel_alanlar_json, sira
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                yarisma_id_sq, st_kodu, sablon, rubrik_aciklamasi,
                min_s, max_s, calc_total,
                json.dumps(asama_ozel, ensure_ascii=False) if asama_ozel else None,
                st_idx
            ])
            asama_id_sq = cur.lastrowid
            total_stages_count += 1

            for c_idx, crit in enumerate(criteria):
                c_id_text = crit.get('id', f'crit_{c_idx}')
                c_name = crit.get('name', 'Kriter')
                max_puan = crit.get('max_score')
                desc = crit.get('description')
                is_mand = 1 if crit.get('is_mandatory') or crit.get('is_required') else 0
                questions = crit.get('guiding_questions', [])

                cur.execute("""
                    INSERT INTO rubrik_kriterleri (
                        asama_id, kriter_id_text, kriter_adi, max_puan,
                        aciklama, is_mandatory, yonlendirici_sorular_json, sira
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    asama_id_sq, c_id_text, c_name, max_puan,
                    desc, is_mand, json.dumps(questions, ensure_ascii=False), c_idx
                ])
                total_criteria_count += 1

            if isinstance(req_sections, dict):
                for b_idx, (sec_key, sec_val) in enumerate(req_sections.items()):
                    is_reg = 1 if is_regex_str(sec_val) else 0
                    cur.execute("""
                        INSERT INTO gerekli_bolumler (
                            asama_id, bolum_anahtari, bolum_degeri, is_regex, sira
                        ) VALUES (?, ?, ?, ?, ?)
                    """, [asama_id_sq, sec_key, str(sec_val), is_reg, b_idx])
                    total_sections_count += 1

        conn.commit()

        # ── 2. Cloudflare D1 Batch Scriptini Olustur ve Gonder ────────────────
        d1_stmts = []

        d1_stmts.append(f"""
            INSERT INTO yarismalar (
                slug, name, kategori_adi, hedef_egitim_seviyesi,
                takim_uye_min, takim_uye_max, danisman_sarti, dil_gereksinimi,
                yurutucu_kurum, etkinlik_yeri, keywords_json, oncelikli_gorevler_json,
                sartname_kisitlari_json, ozel_alanlar_json, logo_r2_key, aktif
            ) VALUES (
                {sql_quote(slug)}, {sql_quote(name)}, {sql_quote(kategori_adi)}, {sql_quote(hedef_egitim_seviyesi)},
                {min_u}, {max_u}, {sql_quote(danisman_sarti)}, {sql_quote(dil)},
                {sql_quote(yurutucu)}, {sql_quote(etkinlik_yeri)},
                {sql_quote(json.dumps(keywords, ensure_ascii=False))},
                {sql_quote(json.dumps(oncelikli_gorevler, ensure_ascii=False))},
                {sql_quote(json.dumps(sartname_kisitlari, ensure_ascii=False))},
                {sql_quote(json.dumps(ozel_alanlar, ensure_ascii=False) if ozel_alanlar else None)},
                {sql_quote(logo_r2)}, 1
            )
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                kategori_adi=excluded.kategori_adi,
                hedef_egitim_seviyesi=excluded.hedef_egitim_seviyesi,
                takim_uye_min=excluded.takim_uye_min,
                takim_uye_max=excluded.takim_uye_max,
                danisman_sarti=excluded.danisman_sarti,
                dil_gereksinimi=excluded.dil_gereksinimi,
                yurutucu_kurum=excluded.yurutucu_kurum,
                etkinlik_yeri=excluded.etkinlik_yeri,
                keywords_json=excluded.keywords_json,
                oncelikli_gorevler_json=excluded.oncelikli_gorevler_json,
                sartname_kisitlari_json=excluded.sartname_kisitlari_json,
                ozel_alanlar_json=excluded.ozel_alanlar_json,
                updated_at=CURRENT_TIMESTAMP
        """)

        d1_stmts.append(f"""
            INSERT INTO competitions (
                competition_id, name, slug, domain, sub_category, levels, description,
                logo_r2_key, publish_status, spec_status, created_at, updated_at
            ) VALUES (
                {sql_quote(slug)}, {sql_quote(name)}, {sql_quote(slug)}, {sql_quote(kategori_adi or 'Teknoloji')},
                NULL, {sql_quote(hedef_egitim_seviyesi)}, NULL, {sql_quote(logo_r2)}, 'yayinda', 'onaylandi',
                {sql_quote(now_iso())}, {sql_quote(now_iso())}
            )
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name, domain=excluded.domain, levels=excluded.levels,
                updated_at=excluded.updated_at
        """)

        d1_stmts.append(f"DELETE FROM yarisma_sartnameleri WHERE yarisma_id IN (SELECT id FROM yarismalar WHERE slug = {sql_quote(slug)})")
        d1_stmts.append(f"DELETE FROM competition_specs WHERE competition_id = {sql_quote(slug)}")

        for s_idx, dosya in enumerate(specifications):
            ext = dosya.split('.')[-1].upper()
            r2_spec = f"yarismalar/{slug}/sartname/{dosya}"
            d1_stmts.append(f"""
                INSERT INTO yarisma_sartnameleri (yarisma_id, dosya_adi, r2_key, dosya_tipi, sira)
                SELECT id, {sql_quote(dosya)}, {sql_quote(r2_spec)}, {sql_quote(ext)}, {s_idx}
                FROM yarismalar WHERE slug = {sql_quote(slug)}
            """)
            branch = f"dal_{s_idx}" if len(specifications) > 1 else None
            d1_stmts.append(f"""
                INSERT INTO competition_specs (spec_id, competition_id, title, branch_code, r2_key, original_name, is_primary, created_at)
                VALUES ({sql_quote(new_id())}, {sql_quote(slug)}, {sql_quote(dosya)}, {sql_quote(branch)}, {sql_quote(r2_spec)}, {sql_quote(dosya)}, {1 if s_idx == 0 else 0}, {sql_quote(now_iso())})
            """)

        d1_stmts.append(f"""
            DELETE FROM rubrik_kriterleri WHERE asama_id IN (
                SELECT a.id FROM yarisma_asamalari a JOIN yarismalar y ON a.yarisma_id = y.id WHERE y.slug = {sql_quote(slug)}
            )
        """)
        d1_stmts.append(f"""
            DELETE FROM gerekli_bolumler WHERE asama_id IN (
                SELECT a.id FROM yarisma_asamalari a JOIN yarismalar y ON a.yarisma_id = y.id WHERE y.slug = {sql_quote(slug)}
            )
        """)
        d1_stmts.append(f"""
            DELETE FROM yarisma_asamalari WHERE yarisma_id IN (
                SELECT id FROM yarismalar WHERE slug = {sql_quote(slug)}
            )
        """)
        d1_stmts.append(f"DELETE FROM competition_stages WHERE competition_id = {sql_quote(slug)}")
        d1_stmts.append(f"DELETE FROM stage_rubric_criteria WHERE competition_id = {sql_quote(slug)}")

        for st_idx, st in enumerate(stages):
            st_kodu = st.get('stage_code_qualified', st.get('stage', 'GENEL'))
            sablon = st.get('template')
            rubric = st.get('rubric', {})
            rubrik_aciklamasi = rubric.get('description')
            min_s = rubric.get('min_pages')
            max_s = rubric.get('max_pages')
            if max_s == 0:
                max_s = None

            criteria = rubric.get('criteria', [])
            req_sections = rubric.get('required_sections', {})

            calc_total = sum([c.get('max_score', 0) for c in criteria if isinstance(c.get('max_score'), (int, float))])
            if calc_total == 0 and any(c.get('max_score') is None for c in criteria):
                calc_total = None

            asama_ozel = {k: v for k, v in st.items() if k not in ('stage', 'template', 'rubric')}

            d1_stmts.append(f"""
                INSERT INTO yarisma_asamalari (
                    yarisma_id, stage_kodu, sablon_adi, rubrik_aciklamasi,
                    min_sayfa, max_sayfa, toplam_puan, ozel_alanlar_json, sira
                ) SELECT id, {sql_quote(st_kodu)}, {sql_quote(sablon)}, {sql_quote(rubrik_aciklamasi)},
                  {sql_quote(min_s)}, {sql_quote(max_s)}, {sql_quote(calc_total)},
                  {sql_quote(json.dumps(asama_ozel, ensure_ascii=False) if asama_ozel else None)}, {st_idx}
                FROM yarismalar WHERE slug = {sql_quote(slug)}
            """)

            sablon_r2 = f"yarismalar/{slug}/sablon/{st_kodu}/{sablon}" if sablon else None
            d1_stmts.append(f"""
                INSERT INTO competition_stages (
                    stage_id, competition_id, stage_code, stage_name, level,
                    sablon_docx_r2_key, max_pages, max_score, required_sections_json,
                    rubric_status, order_index, created_at
                ) VALUES (
                    {sql_quote(new_id())}, {sql_quote(slug)}, {sql_quote(st_kodu)}, {sql_quote(st_kodu)}, 'Genel',
                    {sql_quote(sablon_r2)}, {max_s or 25}, {calc_total or 100.0},
                    {sql_quote(json.dumps(req_sections, ensure_ascii=False) if req_sections else None)},
                    'onaylandi', {st_idx}, {sql_quote(now_iso())}
                )
            """)

            for c_idx, crit in enumerate(criteria):
                c_id_text = crit.get('id', f'crit_{c_idx}')
                c_name = crit.get('name', 'Kriter')
                max_puan = crit.get('max_score')
                desc = crit.get('description')
                is_mand = 1 if crit.get('is_mandatory') or crit.get('is_required') else 0
                questions = crit.get('guiding_questions', [])

                d1_stmts.append(f"""
                    INSERT INTO rubrik_kriterleri (
                        asama_id, kriter_id_text, kriter_adi, max_puan,
                        aciklama, is_mandatory, yonlendirici_sorular_json, sira
                    ) SELECT a.id, {sql_quote(c_id_text)}, {sql_quote(c_name)}, {sql_quote(max_puan)},
                      {sql_quote(desc)}, {is_mand}, {sql_quote(json.dumps(questions, ensure_ascii=False))}, {c_idx}
                    FROM yarisma_asamalari a JOIN yarismalar y ON a.yarisma_id = y.id
                    WHERE y.slug = {sql_quote(slug)} AND a.stage_kodu = {sql_quote(st_kodu)}
                """)

                crit_code = f"C{c_idx+1}"
                d1_stmts.append(f"""
                    INSERT INTO stage_rubric_criteria (
                        criterion_id, competition_id, stage_code, level,
                        criterion_code, criterion_name, description, max_score,
                        approved_by_admin, order_index, created_at
                    ) VALUES (
                        {sql_quote(new_id())}, {sql_quote(slug)}, {sql_quote(st_kodu)}, 'Genel',
                        {sql_quote(crit_code)}, {sql_quote(c_name)}, {sql_quote(desc)},
                        {float(max_puan) if max_puan is not None else 0.0},
                        1, {c_idx}, {sql_quote(now_iso())}
                    )
                """)

            if isinstance(req_sections, dict):
                for b_idx, (sec_key, sec_val) in enumerate(req_sections.items()):
                    is_reg = 1 if is_regex_str(sec_val) else 0
                    d1_stmts.append(f"""
                        INSERT INTO gerekli_bolumler (
                            asama_id, bolum_anahtari, bolum_degeri, is_regex, sira
                        ) SELECT a.id, {sql_quote(sec_key)}, {sql_quote(str(sec_val))}, {is_reg}, {b_idx}
                        FROM yarisma_asamalari a JOIN yarismalar y ON a.yarisma_id = y.id
                        WHERE y.slug = {sql_quote(slug)} AND a.stage_kodu = {sql_quote(st_kodu)}
                    """)

        d1_exec_batch(d1_stmts)

        success_count += 1
        print(f"  [{idx:02d}/60] [OK] {slug:45} -> {len(stages)} asama, {len(specifications)} sartname", flush=True)

    conn.close()

    print("\n" + "="*70, flush=True)
    print("ISLEM BASARIYLA TAMAMLANDI!", flush=True)
    print(f"  * Aktarilan Yarisma:       {success_count} adet", flush=True)
    print(f"  * Aktarilan Sartname:      {total_specs_count} adet", flush=True)
    print(f"  * Aktarilan Asama:         {total_stages_count} adet", flush=True)
    print(f"  * Aktarilan Kriter:        {total_criteria_count} adet", flush=True)
    print(f"  * Aktarilan Bolum Isteri:  {total_sections_count} adet", flush=True)
    print("="*70, flush=True)


if __name__ == '__main__':
    init_database_tables()
    import_competitions()
