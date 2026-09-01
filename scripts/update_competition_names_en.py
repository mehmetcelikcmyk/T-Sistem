"""
Cloudflare D1 — competitions tablosuna name_en (İngilizce ad) ekler.
"""
import requests, json

ACCOUNT_ID = "fad19865339b3a1dc3e3de4901a451bf"
DB_ID      = "158fadb7-cc38-4692-8c99-4400eefc8d52"
TOKEN      = "cfut_JTuvlaNx2MxlRZxgJ0HGPM5ZW8uCr2cokGc63t1wbf36def6"
D1_URL     = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# slug → English name mapping (60 competitions)
NAME_EN_MAP = {
    "5g-yapay-zeka-ile-akilli-yol-guvenligi-yarismasi":
        "Smart Road Safety with 5G & AI Competition",
    "bagimliliklarla-mucadelede-teknolojik-uygulamalar-yarismasi":
        "Technological Applications in Fighting Addictions Competition",
    "biyoteknoloji-inovasyon-yarismasi":
        "Biotechnology Innovation Competition",
    "blokzincir-yarismasi":
        "Blockchain Competition",
    "dikey-inisli-roket-yarismasi":
        "Vertical Landing Rocket Competition",
    "e-ticaret-yarismasi":
        "E-Commerce Hackathon Competition",
    "elektronik-harp-yarismasi":
        "Electronic Warfare Competition",
    "fpv-drone-izleme-tracking-yarismasi":
        "FPV Drone Tracking Competition",
    "finansal-teknolojiler-yarismasi":
        "Financial Technologies Competition",
    "hackmasters-guneydogu":
        "Hack Masters Southeast Cybersecurity Competition",
    "hareketli-uydu-terminali-yarismasi":
        "Mobile Satellite Terminal Competition",
    "havacilikta-yapay-zeka-yarismasi":
        "Artificial Intelligence in Aviation Competition",
    "hyperloop-gelistirme-yarismasi":
        "Hyperloop Development Competition",
    "jet-motor-tasarim-yarismasi":
        "Jet Engine Design Competition",
    "kuantum-teknolojileri-yarismasi":
        "Quantum Technologies Competition (Hardware Category)",
    "kure-teknofest-mavi-vatan-madde-yazim-yarismasi":
        "KÜRE | TEKNOFEST Blue Homeland Article & Blog Writing Competition",
    "teknofest-mesleki-yetenek-yarismasi":
        "Vocational Skills Competition",
    "savasan-iha-avci-drone-yarismasi":
        "Combat UAV Hunter Drone Competition",
    "savasan-iha-yarismasi":
        "Combat UAV Competition",
    "savasan-iha-yildizlar-yarismasi":
        "Combat UAV Stars Competition",
    "su-alti-roket-yarismasi":
        "Underwater Rocket Competition",
    "suru-iha-yarismasi":
        "Swarm UAV Competition",
    "sifir-atik-dongusel-ekonomi-yarismasi":
        "Zero Waste & Circular Economy Competition",
    "teknofest-drone-sampiyonasi":
        "TEKNOFEST Drone Championship",
    "maden-teknolojileri-yarismasi":
        "TEKNOFEST Mining Technologies Competition",
    "mavi-vatan-resim-yarismasi":
        "TEKNOFEST Blue Homeland Painting Competition",
    "teknofest-mimari-ve-gorsel-tasarim-yarismasi":
        "TEKNOFEST Architectural and Visual Design Competition",
    "nsosyal-inovasyon-yarismasi":
        "TEKNOFEST NSocial Innovation Competition",
    "nukleer-enerji-teknolojileri-tasarim-yarismasi":
        "TEKNOFEST Nuclear Energy Technologies Design Competition",
    "onkolojide-3t-yarismasi":
        "TEKNOFEST Oncology 3T (Diagnosis, Treatment, Follow-up) Competition",
    "pardus-hata-yakalama-ve-oneri-yarismasi":
        "TEKNOFEST Pardus Bug Hunting & Suggestion Competition",
    "teknofest-robolig-yarismasi":
        "TEKNOFEST RoboLeague Competition",
    "robotaksi-binek-otonom-arac-yarismasi":
        "TEKNOFEST Robotaxi Autonomous Vehicle Competition",
    "roket-yarismasi":
        "TEKNOFEST Rocket Competition",
    "sanayide-robotik-uygulamalar-yarismasi":
        "TEKNOFEST Industrial Robotics Applications Competition",
    "saglikta-yapay-zeka-yarismasi":
        "TEKNOFEST Artificial Intelligence in Healthcare Competition",
    "model-uydu-yarismasi":
        "TEKNOFEST TÜRKSAT Model Satellite Competition",
    "world-drone-cup":
        "TEKNOFEST World Drone Cup 2026",
    "yapay-zeka-destekli-havayolu-optimizasyonu-yarismasi":
        "TEKNOFEST AI-Powered Airline Route Optimization Competition",
    "yapay-zeka-destekli-lojistik-anahat-optimizasyonu-yarismasi":
        "TEKNOFEST AI-Powered Logistics Backbone Optimization Competition",
    "yapay-zeka-dil-ajanlari-yarismasi":
        "TEKNOFEST AI Language Agents Competition",
    "teknofest-yapay-zeka-film-yarismasi":
        "TEKNOFEST AI Film Competition",
    "tarim-teknolojileri-yarismasi":
        "Agricultural Technologies Competition",
    "tuba-teknofest-doktora-bilim-odulleri":
        "TÜBA-TEKNOFEST Doctoral Science Awards",
    "lise-ogrencileri-kutup-arastirma-projeleri-yarismasi":
        "TÜBİTAK 2204-C High School Students Polar Research Projects Competition",
    "lise-ogrencileri-iklim-degisikligi-arastirma-projeleri-yarismasi":
        "TÜBİTAK 2204-D High School Students Climate Change Research Projects Competition",
    "universite-ogrencileri-arastirma-proje-yarismalari":
        "TÜBİTAK 2242 University Students Research Project Competitions",
    "liseler-arasi-insansiz-hava-araclari-yarismasi":
        "TÜBİTAK Inter-High School Unmanned Aerial Vehicles Competition",
    "uluslararasi-elektrikli-arac-yarislari":
        "International Electric Vehicle Races",
    "uluslararasi-insansiz-hava-araci-yarismasi":
        "International Unmanned Aerial Vehicle Competition",
    "celikkubbe-hava-savunma-sistemleri-yarismasi":
        "Steel Dome Air Defense Systems Competition",
    "cip-tasarim-yarismasi":
        "Chip Design Competition",
    "ileri-otonom-sistemler-tasarim-ve-operasyon-yarismasi":
        "Advanced Autonomous Systems Design and Operation Competition",
    "insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi":
        "Technologies for Humanity Competition - High School Level",
    "insanlik-yararina-teknolojiler-yarismasi-ortaokul-seviyesi":
        "Technologies for Humanity Competition - Middle School Level",
    "insanlik-yararina-teknolojiler-yarismasi-ilkokul-seviyesi":
        "Technologies for Humanity Competition - Elementary School Level",
    "insansiz-deniz-araci-yarismasi":
        "Unmanned Surface Vehicle Competition",
    "insansiz-kara-araci-yarismasi":
        "Unmanned Ground Vehicle Competition",
    "insansiz-su-alti-sistemleri-yarismasi":
        "Unmanned Underwater Systems Competition",
    "insansiz-su-alti-sistemleri-yildizlar-yarismasi":
        "Unmanned Underwater Systems Stars Competition",
}


def run_query(sql: str, params: list | None = None):
    body = {"sql": sql}
    if params:
        body["params"] = params
    r = requests.post(D1_URL, headers=HEADERS, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"D1 error: {data.get('errors')}")
    return data


def main():
    # 1. Önce name_en kolonu yoksa ekle (idempotent)
    print("Checking/adding name_en column...")
    try:
        run_query("ALTER TABLE competitions ADD COLUMN name_en TEXT;")
        print("  → name_en column added.")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("  → name_en column already exists, skipping ALTER.")
        else:
            print(f"  → ALTER result (may be OK): {e}")

    # 2. Her yarışma için UPDATE
    print(f"\nUpdating {len(NAME_EN_MAP)} competitions...")
    ok = 0
    fail = 0
    for slug, name_en in NAME_EN_MAP.items():
        sql = "UPDATE competitions SET name_en = ? WHERE competition_id = ?;"
        try:
            result = run_query(sql, [name_en, slug])
            results = result.get("result", [{}])
            rows_changed = results[0].get("meta", {}).get("changes", "?") if results else "?"
            print(f"  ✓ {slug[:55]:<55} → changes={rows_changed}")
            ok += 1
        except Exception as e:
            print(f"  ✗ {slug}: {e}")
            fail += 1

    print(f"\nDone. Success={ok}, Failed={fail}")

    # 3. Sonucu doğrula
    print("\nVerification (first 10 rows with name_en):")
    try:
        res = run_query(
            "SELECT competition_id, name, name_en FROM competitions WHERE name_en IS NOT NULL LIMIT 10;"
        )
        rows = res["result"][0].get("results", []) if res.get("result") else []
        for row in rows:
            print(f"  {row.get('competition_id','')[:40]:<40} | {row.get('name_en','')}")
        if not rows:
            print("  (no rows returned — competitions table may still be empty)")
    except Exception as e:
        print(f"  Verification error: {e}")


if __name__ == "__main__":
    main()
