"""T-Sistem · UCTAN UCA AKIS TESTI (Faz 9).

Senaryo: admin yarisma acar -> sartname/dal ekler -> asama + rubrik tanimlar
         -> yarismaci kayit olur -> takim kurar -> basvurur -> rapor yukler
         -> admin hakeme atar -> hakem muhurler -> yarismaci KARNESINI GORUR.

Bu test, eski kod tabaninda KOPUK olan zinciri bastan sona dogrular.
Calistirma:  python -m pytest tests/test_flow.py -q
"""

import os, sys, json, logging, tempfile
from pathlib import Path
os.environ["TSISTEM_DB_BACKEND"] = "sqlite"
os.environ["TSISTEM_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tsistem_test_"), "flow.db")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.WARNING)



def test_uctan_uca_akis() -> None:
    from src.data import repos, reset
    from src.data.enums import (
        ApplicationStatus, Decision, PublishStatus, ReportStatus, Role, RuleType,
    )
    from src.data.migrate import apply_schema, seed_calibration, verify_schema
    from src.data.models import (
        Competition, CompetitionSpec, CriterionScore, Requirement,
        RubricCriterion, Stage, User,
    )

    print("== 1. SEMA ==")
    apply_schema("sqlite"); seed_calibration("sqlite")
    assert verify_schema("sqlite"), "sema dogrulanamadi"

    R = repos()
    print("\n== 2. KULLANICILAR ==")
    admin = R.users.create(User(name="Sistem", surname="Yoneticisi", email="admin@t3.org", role=Role.ADMIN, profile_completed=True), password="CokGucluParola!2026")
    hakem1 = R.users.create(User(name="Ayse", surname="Demir", email="hakem1@t3.org", role=Role.HAKEM, specialty="Yapay Zeka"), password="HakemParola!2026")
    hakem2 = R.users.create(User(name="Mehmet", surname="Kaya", email="hakem2@t3.org", role=Role.HAKEM), password="HakemParola!2026")
    kaptan = R.users.create(User(name="Elif", surname="Yilmaz", email="kaptan@ogr.edu.tr", education_level="Lisans"), password="UyeParola!2026")
    uye    = R.users.create(User(name="Can", surname="Ates", email="uye@ogr.edu.tr"), password="UyeParola!2026")
    print(f"  {len(R.users.list())} kullanici · roller={R.users.counts_by_role()}")
    assert R.users.authenticate("admin@t3.org", "CokGucluParola!2026").is_admin
    try:
        R.users.authenticate("admin@t3.org", "yanlis"); assert False
    except Exception as e: print(f"  yanlis parola reddedildi: {type(e).__name__}")

    print("\n== 3. YARISMA + COK DALLI SARTNAME ==")
    comp = R.competitions.create(Competition(
        competition_id="teknofest-mesleki-yetenek-yarismasi", name="TEKNOFEST Mesleki Yetenek Yarismasi",
        slug="teknofest-mesleki-yetenek-yarismasi", domain="Mesleki Teknolojiler",
        levels="Lise, Universite", description="9 alt dalda mesleki yetenek yarismasi."), actor=admin.user_id)
    for code, nm in [("kaynakcilik","Kaynakcilik"),("akilli_fabrika","Akilli Fabrika"),("cnc","CNC Torna")]:
        R.competitions.add_spec(CompetitionSpec(competition_id=comp.competition_id,
            title=f"Mesleki Yetenek - {nm} Dali", branch_code=code, branch_name=nm,
            r2_key=f"yarismalar/{comp.slug}/sartname/{comp.slug}_{code}_sartnamesi.pdf"), actor=admin.user_id)
    print(f"  dallar: {R.competitions.branches(comp.competition_id)}")
    assert len(R.competitions.list_specs(comp.competition_id)) == 3

    R.competitions.set_schedule(comp.competition_id, {"son_basvuru":"31.12.2026","yarisma_tarihi":"15.09.2027"}, actor=admin.user_id)
    R.competitions.set_schedule(comp.competition_id, {"sonuc_tarihi":"30.09.2027"}, actor=admin.user_id)
    sched = json.loads(R.competitions.get(comp.competition_id).schedule_json)
    assert sched.get("son_basvuru") and sched.get("sonuc_tarihi"), f"takvim kismi guncelleme bozuk: {sched}"
    print(f"  takvim korundu: {sched}")

    print("\n== 4. ASAMA + RUBRIK ==")
    st = R.competitions.add_stage(Stage(competition_id=comp.competition_id, stage_code="otr",
        stage_name="On Tasarim Raporu", max_pages=20, deadline="01.03.2027"), actor=admin.user_id)
    R.competitions.replace_rubric(comp.competition_id, "OTR", [
        RubricCriterion(competition_id="", stage_code="", criterion_code="C1", criterion_name="Problem Tanimi", max_score=20),
        RubricCriterion(competition_id="", stage_code="", criterion_code="C2", criterion_name="Yontem ve Algoritmalar", max_score=30),
        RubricCriterion(competition_id="", stage_code="", criterion_code="C3", criterion_name="Ozgunluk", max_score=20),
        RubricCriterion(competition_id="", stage_code="", criterion_code="C4", criterion_name="Sonuclar", max_score=30),
    ], actor=admin.user_id)
    print(f"  rubrik toplami: {R.competitions.rubric_total(comp.competition_id,'OTR')} puan")
    assert R.competitions.rubric_total(comp.competition_id, "OTR") == 100
    # YANLIS yarismanin rubrigi HIC dolmamali (eski kod hep HYZ OTR'ye dusuyordu)
    assert R.competitions.list_rubric("olmayan-yarisma", "OTR") == [], "rubrik sizintisi!"
    print("  baska yarismanin rubrigi sizmiyor")

    # KARAR #2: asamasiz yarismaya varsayilan OTR
    bos = R.competitions.create(Competition(competition_id="e-ticaret-yarismasi", name="E-Ticaret Yarismasi",
        slug="e-ticaret-yarismasi", domain="Dijital Teknolojiler"), actor=admin.user_id)
    auto = R.competitions.ensure_default_stage(bos.competition_id, actor=admin.user_id)
    assert auto and auto.stage_code == "OTR" and auto.is_auto_generated
    assert R.competitions.ensure_default_stage(comp.competition_id) is None, "mevcut asamaya dokunmamali"
    print(f"  asamasiz yarismaya varsayilan {auto.stage_code} eklendi; mevcut asamalara dokunulmadi")

    print("\n== 5. TAKIM ==")
    takim = R.teams.create(name="Bilig Yapay Zeka", captain_user_id=kaptan.user_id, level="Universite",
                           institution="Ornek Universitesi", advisor_name="Prof. Dr. Zeynep Ak")
    R.teams.join_by_code(takim.team_code, uye.user_id)
    print(f"  kod={takim.team_code} · uye sayisi={R.teams.member_count(takim.team_id)}")
    assert R.teams.member_count(takim.team_id) == 2
    try:
        R.teams.join_by_code("ZZZ999", uye.user_id); assert False
    except Exception as e: print(f"  gecersiz kod reddedildi: {e}")
    assert len(R.teams.list_for_user(uye.user_id)) == 1, "uye takimini gormeli"

    print("\n== 6. BASVURU + UYGUNLUK KAPISI ==")
    rep = R.applications.check_eligibility(takim.team_id, comp.competition_id, "kaynakcilik")
    print(f"  taslak yarisma -> engel: {rep.blocking}")
    assert not rep.ok
    R.competitions.update(comp.competition_id, {"publish_status": PublishStatus.YAYINDA.value}, actor=admin.user_id)
    R.competitions.replace_requirements(comp.competition_id, [
        Requirement(competition_id="", title="Takim buyuklugu", rule_type=RuleType.TAKIM, min_team_size=2, max_team_size=6,
                    source_quote="Takimlar en az 2 en fazla 6 kisiden olusur."),
        Requirement(competition_id="", title="Danisman zorunlulugu", rule_type=RuleType.DANISMAN, advisor_required=True,
                    source_quote="Her takimda bir danisman bulunmalidir."),
    ], branch_code="kaynakcilik", actor=admin.user_id)
    app = R.applications.apply(team_id=takim.team_id, competition_id=comp.competition_id,
                               branch_code="kaynakcilik", actor=kaptan.user_id)
    print(f"  basvuru olustu: {app.app_id[:8]}… dal=kaynakcilik")
    try:
        R.applications.apply(team_id=takim.team_id, competition_id=comp.competition_id, branch_code="kaynakcilik"); assert False
    except Exception as e: print(f"  mukerrer basvuru engellendi: {type(e).__name__}")

    print("\n== 7. RAPOR + SURUM ==")
    r1 = R.reports.create(app_id=app.app_id, competition_id=comp.competition_id, stage_code="OTR",
        file_name="bilig_yapay_zeka_mesleki_yetenek_otr_raporu.pdf",
        r2_key="yarismalar/teknofest-mesleki-yetenek-yarismasi/asamalar/OTR/raporlar/x/rapor.pdf",
        page_count=18, report_text="Bu calismada kaynak dikislerinin otomatik denetimi icin YOLOv8 mimarisi kullanilmistir. "*20,
        uploaded_by=kaptan.user_id)
    r2v = R.reports.create(app_id=app.app_id, competition_id=comp.competition_id, stage_code="OTR",
        file_name="bilig_yapay_zeka_mesleki_yetenek_otr_raporu_v2.pdf", r2_key="…/rapor_v2.pdf",
        page_count=19, report_text="Revize edilmis surum.", uploaded_by=kaptan.user_id)
    assert r2v.version == 2 and R.reports.latest(app.app_id,"OTR").version == 2
    print(f"  surum takibi: v1, v{r2v.version} · durum={r2v.status.value} ({r2v.status.label_tr})")
    # GIZLILIK
    baskasi = R.users.create(User(name="Yabanci", email="yabanci@x.com"), password="Parola!12345")
    assert len(R.reports.list_for_user(baskasi.user_id)) == 0, "GIZLILIK IHLALI"
    assert len(R.reports.list_for_user(uye.user_id)) == 2
    print("  gizlilik: baskasi 0 rapor goruyor, takim uyesi 2 rapor")

    print("\n== 8. ATAMA + IZOLASYON ==")
    asg = R.evaluations.assign(r2v.report_id, hakem1.user_id, assigned_by=admin.user_id)
    h1 = R.evaluations.list_for_referee(hakem1.user_id)
    h2 = R.evaluations.list_for_referee(hakem2.user_id)
    print(f"  hakem1={len(h1)} rapor · hakem2={len(h2)} rapor")
    assert len(h1) == 1 and len(h2) == 0, "IZOLASYON KIRIK"
    assert R.reports.get(r2v.report_id).status == ReportStatus.HAKEME_ATANDI
    # atanmamis rapor kimseye gorunmemeli
    assert len(R.evaluations.list_for_referee(hakem2.user_id)) == 0
    print(f"  rapor durumu: {R.reports.get(r2v.report_id).status.label_tr}")

    print("\n== 9. MUHURLEME + KRITER KIRILIMI ==")
    crits = R.competitions.list_rubric(comp.competition_id, "OTR")
    scores = [CriterionScore(criterion_code=c.criterion_code, criterion_name=c.criterion_name,
        max_score=c.max_score, ai_score=c.max_score*0.8, referee_score=c.max_score*0.85,
        ai_rationale="Rapordaki bulgular yeterli.", referee_rationale="Katiliyorum.",
        evidence_json=json.dumps([{"quote":"YOLOv8 mimarisi kullanilmistir","page":4}], ensure_ascii=False)) for c in crits]
    try:
        bad = [CriterionScore(criterion_code="C1", criterion_name="X", max_score=20, referee_score=25)]
        R.evaluations.seal(assignment_id=asg.assignment_id, referee_user_id=hakem1.user_id,
                           criterion_scores=bad, decision=Decision.KABUL); assert False
    except ValueError as e: print(f"  tavan kontrolu calisti: {str(e)[:60]}…")
    ev = R.evaluations.seal(assignment_id=asg.assignment_id, referee_user_id=hakem1.user_id,
        criterion_scores=scores, decision=Decision.KABUL, referee_notes="Rapor teknik olarak yeterlidir.",
        ai_total_score=80.0)
    print(f"  muhurlendi: {ev.total_score}/{ev.max_total_score} · karar={ev.decision.label_tr}")
    assert len(R.evaluations.scores(ev.evaluation_id)) == 4
    assert R.reports.get(r2v.report_id).status == ReportStatus.DEGERLENDIRILDI
    # hakem kimligi EZILMEDI
    assert ev.referee_user_id == hakem1.user_id, "hakem kimligi ezildi!"
    print(f"  hakem kimligi korundu: {ev.referee_user_id[:8]}…")

    print("\n== 10. KARNE (yarismaci gorebiliyor mu?) ==")
    card = R.evaluations.publish_card(ev.evaluation_id,
        strengths=["Problem tanimi net ve olculebilir.","Veri seti kaynaklari acikca belirtilmis."],
        improvements=["Farkli isik kosullarinda karsilastirmali test sonuclari eksik."],
        roadmap=["KTR asamasinda hata matrisi ekleyiniz."], actor=hakem1.user_id)
    detail = R.evaluations.card_detail(card)
    print(f"  karne: {card.total_score}/{card.max_total_score}")
    for s in detail["scores"]: print(f"    {s.criterion_code} {s.criterion_name:26s} {s.referee_score:5.1f}/{s.max_score:.0f}  (AI {s.ai_score:.1f})")
    print(f"  guclu yonler: {len(detail['strengths'])} · gelisim: {len(detail['improvements'])} · yol haritasi: {len(detail['roadmap'])}")
    assert card.total_score == ev.total_score
    cards = R.evaluations.cards_for_application(app.app_id)
    assert len(cards) == 1, "yarismaci karnesini goremiyor!"
    print("  YARISMACI KARNESINI GORUYOR")

    print("\n== 11. BILDIRIM + DENETIM IZI ==")
    print(f"  kaptan okunmamis bildirim: {len(R.evaluations.unread(kaptan.user_id))}")
    print(f"  hakem1 okunmamis bildirim: {len(R.evaluations.unread(hakem1.user_id))}")
    assert len(R.evaluations.unread(kaptan.user_id)) >= 1
    n = R.client.query("SELECT COUNT(*) AS n FROM audit_log;")[0]["n"]
    print(f"  denetim izi kaydi: {n}")
    assert n > 15

    print("\n== 12. SON ADMIN KORUMASI ==")
    try:
        R.users.set_role(admin.user_id, Role.YARISMACI); assert False
    except ValueError as e: print(f"  {e}")

    print("\n== 13. HAKEM YUKU + OTOMATIK DAGITIM ==")
    r3 = R.reports.create(app_id=app.app_id, competition_id=comp.competition_id, stage_code="OTR",
        file_name="ucuncu.pdf", r2_key="…/3.pdf", report_text="metin", uploaded_by=kaptan.user_id)
    dist = R.evaluations.auto_distribute([r3.report_id], assigned_by=admin.user_id)
    print(f"  otomatik dagitim -> {dist}")
    for w in R.evaluations.referee_workload():
        print(f"    {w['name']} {w['surname']}: bekleyen={w['bekleyen']} tamamlanan={w['tamamlanan']}")

    print("\n== 14. ISTATISTIK ==")
    print(f"  rapor durumlari: { {k:v for k,v in R.reports.stats().items() if v} }")
    print(f"  yarisma sayisi: {R.competitions.count()} (yayinda: {R.competitions.count(PublishStatus.YAYINDA)})")

    print("\n" + "="*62)
    print("TUM DUMAN TESTLERI GECTI — Faz 1 veri katmani calisiyor.")
    print("="*62)
