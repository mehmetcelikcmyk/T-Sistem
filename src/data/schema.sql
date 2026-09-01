-- ═══════════════════════════════════════════════════════════════════════════
-- T-SİSTEM · TEK ŞEMA KAYNAĞI
-- ═══════════════════════════════════════════════════════════════════════════
-- Bu dosya HEM Cloudflare D1 HEM yerel SQLite icin kullanilir.
-- Uygulama:  python -m src.data.migrate --apply --target both
-- Dogrulama: python -m src.data.migrate --verify
--
-- KURAL: Kodda gecen her tablo ve kolon BU DOSYADA tanimli olmak zorundadir.
--        CI testi (tests/test_schema_contract.py) bunu dogrular.
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
-- 1. KIMLIK
-- ───────────────────────────────────────────────────────────────────────────
-- KARAR: Eski `users` tablosu KALDIRILDI. `auth_users` tek kullanici kaynagidir.
--        `specialty` kolonu eski users tablosundan buraya tasindi.

CREATE TABLE IF NOT EXISTS auth_users (
    user_id            TEXT PRIMARY KEY,
    username           TEXT,
    name               TEXT NOT NULL,
    surname            TEXT,
    email              TEXT NOT NULL UNIQUE,
    password_hash      TEXT,
    role               TEXT NOT NULL DEFAULT 'yarismaci'
                       CHECK (role IN ('yarismaci', 'hakem', 'admin')),
    institution        TEXT,
    department         TEXT,
    graduation_status  TEXT,
    tc_citizen         TEXT,
    gender             TEXT,
    birth_date         TEXT,
    phone              TEXT,
    address            TEXT,
    education_level    TEXT,
    specialty          TEXT,
    auth_provider      TEXT NOT NULL DEFAULT 'local'
                       CHECK (auth_provider IN ('local', 'google')),
    profile_completed  INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'aktif'
                       CHECK (status IN ('aktif', 'pasif')),
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_role   ON auth_users(role, status);
CREATE INDEX IF NOT EXISTS idx_users_email  ON auth_users(email);


-- ───────────────────────────────────────────────────────────────────────────
-- 2. YARISMA
-- ───────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS competitions (
    competition_id   TEXT PRIMARY KEY,          -- slug ile ayni
    name             TEXT NOT NULL,             -- insan okunabilir tam ad (Türkçe)
    name_en          TEXT,                      -- İngilizce ad (opsiyonel)
    slug             TEXT NOT NULL UNIQUE,      -- ON CONFLICT hedefi
    domain           TEXT NOT NULL,             -- Havacilik, Yapay Zeka, Saglik...
    sub_category     TEXT,
    levels           TEXT,                      -- "Lise, Universite" (virgullu)
    description      TEXT,                      -- yarismanin amaci/aciklamasi
    logo_r2_key      TEXT,
    schedule_json    TEXT,                      -- {son_basvuru, yarisma_tarihi, sonuc_tarihi}
    awards_json      TEXT,
    publish_status   TEXT NOT NULL DEFAULT 'taslak'
                     CHECK (publish_status IN ('taslak', 'yayinda', 'kapali')),
    spec_status      TEXT NOT NULL DEFAULT 'bekleniyor'
                     CHECK (spec_status IN ('bekleniyor', 'yuklendi', 'analiz_edildi', 'onaylandi')),
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_comp_domain  ON competitions(domain);
CREATE INDEX IF NOT EXISTS idx_comp_publish ON competitions(publish_status);


-- KARAR (#1): Cok sartnameli yarismalarda BIRLESTIRME YAPILMAZ.
-- Her sartname ayri satir, `branch_code` ile izole edilir.
-- Ornek: teknofest-mesleki-yetenek 9 dal, hyperloop 7, elektrikli-arac 7, dil-ajanlari 3
CREATE TABLE IF NOT EXISTS competition_specs (
    spec_id         TEXT PRIMARY KEY,
    competition_id  TEXT NOT NULL,
    title           TEXT NOT NULL,             -- "Mesleki Yetenek - Kaynakcilik Dali"
    branch_code     TEXT,                      -- kaynakcilik / akilli_fabrika / senaryo_2 ...
    branch_name     TEXT,                      -- "Kaynakcilik"
    r2_key          TEXT NOT NULL,
    original_name   TEXT,
    page_count      INTEGER,
    is_primary      INTEGER NOT NULL DEFAULT 0,
    analyzed_at     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    UNIQUE (competition_id, branch_code),
    FOREIGN KEY (competition_id) REFERENCES competitions(competition_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_specs_comp ON competition_specs(competition_id);


CREATE TABLE IF NOT EXISTS competition_stages (
    stage_id                TEXT PRIMARY KEY,
    competition_id          TEXT NOT NULL,
    stage_code              TEXT NOT NULL,     -- OTR, KTR, FTR, ODR, PDR, TTR, PSR...
    stage_name              TEXT NOT NULL,     -- "On Tasarim Raporu"
    level                   TEXT NOT NULL DEFAULT 'Genel',
    branch_code             TEXT,              -- dala ozel asama (opsiyonel)
    sablon_docx_r2_key      TEXT,
    sablon_pdf_r2_key       TEXT,
    max_pages               INTEGER NOT NULL DEFAULT 25,
    max_score               REAL NOT NULL DEFAULT 100.0,
    passing_score           REAL NOT NULL DEFAULT 70.0,
    quota_limit             INTEGER,
    revision_min_score      REAL NOT NULL DEFAULT 60.0,
    stage_status            TEXT NOT NULL DEFAULT 'DEGERLENDIRMEDE'
                            CHECK (stage_status IN ('DEGERLENDIRMEDE', 'HESAPLANDI', 'ILAN_EDILDI')),
    deadline                TEXT,
    font_and_margins        TEXT,
    required_sections_json  TEXT,
    is_auto_generated       INTEGER NOT NULL DEFAULT 0,  -- KARAR #2: varsayilan OTR mi
    rubric_status           TEXT NOT NULL DEFAULT 'bekleniyor'
                            CHECK (rubric_status IN ('bekleniyor', 'cikarildi', 'onaylandi')),
    order_index             INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    updated_at              TEXT,
    UNIQUE (competition_id, stage_code, level, branch_code),
    FOREIGN KEY (competition_id) REFERENCES competitions(competition_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_stages_comp ON competition_stages(competition_id, order_index);


-- Sartnameden AI ile cikarilan, admin tarafindan onaylanan kurallar
CREATE TABLE IF NOT EXISTS competition_requirements (
    req_id            TEXT PRIMARY KEY,
    competition_id    TEXT NOT NULL,
    spec_id           TEXT,                    -- hangi dalin sartnamesinden geldi
    branch_code       TEXT,
    rule_type         TEXT NOT NULL
                      CHECK (rule_type IN ('takim', 'danisman', 'teknik', 'katilim', 'dil', 'diger')),
    title             TEXT NOT NULL,
    description       TEXT,
    min_team_size     INTEGER,
    max_team_size     INTEGER,
    advisor_required  INTEGER NOT NULL DEFAULT 0,
    target_level      TEXT,
    is_mandatory      INTEGER NOT NULL DEFAULT 1,
    source_quote      TEXT,                    -- sartnamedeki dayanak cumle (AI zorunlu doldurur)
    source_page       INTEGER,
    approved_by_admin INTEGER NOT NULL DEFAULT 0,
    order_index       INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (competition_id) REFERENCES competitions(competition_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_req_comp ON competition_requirements(competition_id, branch_code);


-- KARAR: Eski `competition_rubrics` tablosu ile CAKISMA olmasin diye YENI AD.
-- Rapor sablonundan AI ile cikarilan, admin tarafindan onaylanan puanlama kriterleri.
CREATE TABLE IF NOT EXISTS stage_rubric_criteria (
    criterion_id      TEXT PRIMARY KEY,
    competition_id    TEXT NOT NULL,
    stage_code        TEXT NOT NULL,
    level             TEXT NOT NULL DEFAULT 'Genel',
    branch_code       TEXT,
    criterion_code    TEXT NOT NULL,           -- C1, C1.1, C2...
    criterion_name    TEXT NOT NULL,
    description       TEXT,
    max_score         REAL NOT NULL,
    parent_code       TEXT,                    -- alt kriter destegi
    source_quote      TEXT,
    approved_by_admin INTEGER NOT NULL DEFAULT 0,
    order_index       INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    UNIQUE (competition_id, stage_code, level, branch_code, criterion_code)
);

CREATE INDEX IF NOT EXISTS idx_rubric_lookup
    ON stage_rubric_criteria(competition_id, stage_code, level);


-- ───────────────────────────────────────────────────────────────────────────
-- 3. TAKIM VE BASVURU
-- ───────────────────────────────────────────────────────────────────────────
-- KARAR: Takimlar bir yarismaya BAGLANMAZ. Bag `applications` tablosundadir.

CREATE TABLE IF NOT EXISTS teams (
    team_id          TEXT PRIMARY KEY,          -- uuid4
    team_code        TEXT NOT NULL UNIQUE,      -- 6 haneli KARARLI davet kodu
    name             TEXT NOT NULL,
    level            TEXT,                      -- Ortaokul / Lise / Universite / Mezun
    institution      TEXT,
    captain_user_id  TEXT NOT NULL,
    advisor_name     TEXT,
    advisor_email    TEXT,
    advisor_title    TEXT,
    status           TEXT NOT NULL DEFAULT 'aktif'
                     CHECK (status IN ('aktif', 'pasif', 'dagitildi')),
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (captain_user_id) REFERENCES auth_users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_teams_captain ON teams(captain_user_id);
CREATE INDEX IF NOT EXISTS idx_teams_code    ON teams(team_code);


CREATE TABLE IF NOT EXISTS team_members (
    team_id       TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    role_in_team  TEXT NOT NULL DEFAULT 'uye'
                  CHECK (role_in_team IN ('kaptan', 'uye', 'danisman')),
    joined_at     TEXT NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_members_user ON team_members(user_id);


CREATE TABLE IF NOT EXISTS applications (
    app_id          TEXT PRIMARY KEY,           -- uuid4
    team_id         TEXT NOT NULL,
    competition_id  TEXT NOT NULL,
    branch_code     TEXT,                       -- cok dalli yarismalarda secilen dal
    level           TEXT,
    status          TEXT NOT NULL DEFAULT 'aktif'
                    CHECK (status IN ('aktif', 'geri_cekildi', 'elendi', 'tamamlandi')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    UNIQUE (team_id, competition_id, branch_code),
    FOREIGN KEY (team_id)        REFERENCES teams(team_id),
    FOREIGN KEY (competition_id) REFERENCES competitions(competition_id)
);

CREATE INDEX IF NOT EXISTS idx_apps_team ON applications(team_id);
CREATE INDEX IF NOT EXISTS idx_apps_comp ON applications(competition_id, status);


-- ───────────────────────────────────────────────────────────────────────────
-- 4. RAPOR VE DEGERLENDIRME
-- ───────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reports (
    report_id       TEXT PRIMARY KEY,           -- uuid4
    app_id          TEXT NOT NULL,
    competition_id  TEXT NOT NULL,
    stage_code      TEXT NOT NULL,
    level           TEXT NOT NULL DEFAULT 'Genel',
    branch_code     TEXT,
    version         INTEGER NOT NULL DEFAULT 1, -- revizyon destegi
    file_name       TEXT NOT NULL,              -- insan okunabilir ad
    r2_key          TEXT NOT NULL,              -- SADECE key, URL degil
    page_count      INTEGER,
    report_text     TEXT,
    status          TEXT NOT NULL DEFAULT 'BEKLEMEDE'
                    CHECK (status IN ('BEKLEMEDE', 'HAKEME_ATANDI', 'DEGERLENDIRILIYOR',
                                      'DEGERLENDIRILDI', 'REVIZYON_ISTENDI', 'REDDEDILDI')),
    security_json   TEXT,
    checks_json     TEXT,
    ai_score        REAL,
    ai_data_json    TEXT,
    uploaded_by     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    referee_score   REAL,
    referee_id      TEXT,
    referee_notes   TEXT,
    feedback_json   TEXT,
    decision        TEXT,
    evaluated_at    TEXT,
    UNIQUE (app_id, stage_code, level, version),
    FOREIGN KEY (app_id) REFERENCES applications(app_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reports_app    ON reports(app_id);
CREATE INDEX IF NOT EXISTS idx_reports_comp   ON reports(competition_id, stage_code);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);


CREATE TABLE IF NOT EXISTS report_assignments (
    assignment_id    TEXT PRIMARY KEY,
    report_id        TEXT NOT NULL,
    referee_user_id  TEXT NOT NULL,
    assigned_by      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'ATANDI'
                     CHECK (status IN ('ATANDI', 'INCELENIYOR', 'TAMAMLANDI', 'IPTAL')),
    assigned_at      TEXT NOT NULL,
    completed_at     TEXT,
    UNIQUE (report_id, referee_user_id),
    FOREIGN KEY (report_id)       REFERENCES reports(report_id) ON DELETE CASCADE,
    FOREIGN KEY (referee_user_id) REFERENCES auth_users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_assign_referee ON report_assignments(referee_user_id, status);
CREATE INDEX IF NOT EXISTS idx_assign_report  ON report_assignments(report_id);


CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id         TEXT PRIMARY KEY,
    assignment_id         TEXT NOT NULL UNIQUE,
    report_id             TEXT NOT NULL,
    referee_user_id       TEXT NOT NULL,
    total_score           REAL NOT NULL,
    ai_total_score        REAL,
    max_total_score       REAL NOT NULL DEFAULT 100.0,
    decision              TEXT NOT NULL
                          CHECK (decision IN ('KABUL', 'REVIZYON', 'RET')),
    referee_notes         TEXT,
    spec_compliance_json  TEXT,                 -- ADIM 3 hakem kararlari
    sealed_at             TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT,
    FOREIGN KEY (assignment_id) REFERENCES report_assignments(assignment_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_eval_report ON evaluations(report_id);


-- Kriter bazli kirilim: denetim izi ve itiraz icin ZORUNLU
CREATE TABLE IF NOT EXISTS evaluation_scores (
    evaluation_id      TEXT NOT NULL,
    criterion_code     TEXT NOT NULL,
    criterion_name     TEXT NOT NULL,
    max_score          REAL NOT NULL,
    ai_score           REAL,
    referee_score      REAL NOT NULL,
    ai_rationale       TEXT,
    referee_rationale  TEXT,
    evidence_json      TEXT,                    -- TUM kanit alintilari (sayfa + karakter araligi)
    order_index        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (evaluation_id, criterion_code),
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(evaluation_id) ON DELETE CASCADE
);


-- KARAR: Karne basvuruya baglidir (kullanicinin #270'teki isteri)
CREATE TABLE IF NOT EXISTS report_cards (
    card_id            TEXT PRIMARY KEY,
    app_id             TEXT NOT NULL,
    report_id          TEXT NOT NULL,
    evaluation_id      TEXT NOT NULL,
    total_score        REAL NOT NULL,
    max_total_score    REAL NOT NULL DEFAULT 100.0,
    strengths_json     TEXT,
    improvements_json  TEXT,
    roadmap_json       TEXT,
    pedagogical_note   TEXT,
    pdf_r2_key         TEXT,
    published_at       TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT,
    UNIQUE (evaluation_id),
    FOREIGN KEY (app_id)        REFERENCES applications(app_id) ON DELETE CASCADE,
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(evaluation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cards_app ON report_cards(app_id);


-- ───────────────────────────────────────────────────────────────────────────
-- 5. BENZERLIK / INTIHAL  (KARAR: HIBRIT — literal + semantik)
-- ───────────────────────────────────────────────────────────────────────────
-- Katman 1 (literal): difflib/n-gram — birebir kopyala-yapistir
-- Katman 2 (semantik): embedding vektoru — parafraz / esanlamli gizleme
-- Vektorler Cloudflare Vectorize'da tutulur; burada yalnizca referans + ozet saklanir.

CREATE TABLE IF NOT EXISTS report_embeddings (
    report_id       TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    page_no         INTEGER,
    vector_id       TEXT NOT NULL,             -- Vectorize icindeki kayit id'si
    model           TEXT NOT NULL,             -- @cf/baai/bge-m3 vb.
    dim             INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (report_id, chunk_index),
    FOREIGN KEY (report_id) REFERENCES reports(report_id) ON DELETE CASCADE
);


-- Vectorize kullanilamadiginda yerel kosinus benzerligi icin vektor govdesi.
-- (Vectorize aktifken bu tablo bos kalir; `report_embeddings.vector_id`
--  Vectorize icindeki kaydi isaret eder.)
CREATE TABLE IF NOT EXISTS report_embedding_vectors (
    report_id    TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    vector_json  TEXT NOT NULL,
    dim          INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (report_id, chunk_index),
    FOREIGN KEY (report_id) REFERENCES reports(report_id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS similarity_results (
    result_id           TEXT PRIMARY KEY,
    report_id           TEXT NOT NULL,
    matched_report_id   TEXT NOT NULL,
    literal_score       REAL NOT NULL DEFAULT 0.0,   -- difflib 0..1
    semantic_score      REAL NOT NULL DEFAULT 0.0,   -- kosinus 0..1
    combined_score      REAL NOT NULL DEFAULT 0.0,
    risk_level          TEXT NOT NULL DEFAULT 'DUSUK'
                        CHECK (risk_level IN ('DUSUK', 'ORTA', 'YUKSEK')),
    matched_spans_json  TEXT,                        -- eslesme parcalari + sayfa no
    engine_version      TEXT,
    created_at          TEXT NOT NULL,
    UNIQUE (report_id, matched_report_id),
    FOREIGN KEY (report_id) REFERENCES reports(report_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sim_report ON similarity_results(report_id, combined_score);


-- ───────────────────────────────────────────────────────────────────────────
-- 6. SISTEM
-- ───────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS calibration_settings (
    key          TEXT PRIMARY KEY,
    value        REAL NOT NULL,
    description  TEXT,
    updated_at   TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS audit_log (
    log_id         TEXT PRIMARY KEY,
    actor_user_id  TEXT,
    actor_email    TEXT,
    action         TEXT NOT NULL,               -- competition.create, report.assign...
    entity_type    TEXT,
    entity_id      TEXT,
    before_json    TEXT,
    after_json     TEXT,
    ip_hint        TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_time   ON audit_log(created_at);


CREATE TABLE IF NOT EXISTS notifications (
    notification_id  TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    kind             TEXT NOT NULL,             -- rapor_atandi, karne_yayinlandi...
    title            TEXT NOT NULL,
    body             TEXT,
    link             TEXT,
    is_read          INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES auth_users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
