"""
FastAPI REST API Rotaları ve Endpoint'leri
T3 Vakfı Problem 4 PRD: Yarışma Yöneticisi, Hakem ve Yarışmacı akışlarını tam bağlar.

BU KATMANIN AKIŞI:
  Yükleme -> dosya güvenliği -> metin çıkarma -> prompt injection etkisizleştirme
  -> KVKK maskeleme -> kalıcı depolama (R2/yerel disk) -> AI 4. Göz -> veritabanı

NOT: Raporlar artık bellekte (dict) DEĞİL, SQLite/Cloudflare D1 veritabanında
tutulur. Sunucu yeniden başladığında veriler korunur.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response, Depends, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import datetime
import uuid

from src.api.schemas import (
    ReportUploadResponse,
    ComprehensiveReportAnalysisResponse,
    RefereeEvaluationRequest,
    RefereeDecisionResponse,
    RefereeChatRequest,
    RefereeChatResponse,
    ContestantFeedbackResponse,
    AdminMetricsResponse,
    CompetitionRubricRequest,
    CompetitionRubricResponse,
)
from src.evaluation.evaluator import evaluate_report_with_ai
from src.feedback.generator import generate_contestant_feedback, generate_feedback_pdf
from src.security.guard import SecurityGuard
from src.security.auth import UserRole, AuthUser, get_current_user, require_roles
from src.database.db import db
from src.utils.storage import storage
from src.ingestion.pdf_loader import load_pdf
from src.checkers.runner import run_all_checks

router = APIRouter(prefix="/api", tags=["TEKNOFEST AI Evaluation System"])

# Metin çıkarma modülü (Birhan / Issue #1) henüz iskelet olduğu için, boş metin
# geldiğinde AI değerlendirmesinin çökmemesi adına kullanılan yer tutucu.
_METIN_YOK_NOTU = (
    "[PDF metin çıkarma modülü henüz aktif değil — bu rapor için metin tabanlı "
    "analiz sınırlı yapılmıştır. Dosya sisteme kaydedilmiştir.]"
)


# ==========================================
# YARDIMCILAR
# ==========================================

def _guvenlik_taramasi(report_text: str) -> tuple:
    """
    SecurityGuard'ı rapor metnine uçtan uca uygular:
      1. Prompt injection tespiti ve ETKİSİZLEŞTİRME (yalnızca bayrak yetmez;
         metin doğrudan LLM promptuna gidiyor)
      2. KVKK maskeleme (tarafsız değerlendirme için kişisel veriler gizlenir)

    Returns:
        (llm_e_gidecek_temiz_metin, security_check_sozlugu)
    """
    notlar: List[str] = []

    temiz_metin, tehditler = SecurityGuard.neutralize_prompt_injection(report_text)
    injection_var = len(tehditler) > 0
    if injection_var:
        notlar.append(
            f"Raporda yapay zekâyı yönlendirmeye çalışan {len(tehditler)} ifade tespit edildi "
            "ve değerlendirmeye girmeden önce metinden çıkarıldı. Hakem dikkatine sunulur."
        )

    temiz_metin, pii_sayim = SecurityGuard.anonymize_kvkk_data(temiz_metin)
    maskelenen = sum(pii_sayim.values())
    if maskelenen:
        notlar.append(
            f"KVKK gereği {maskelenen} kişisel veri (TCKN/telefon/e-posta) maskelendi."
        )

    risk = "HIGH" if injection_var else ("MEDIUM" if maskelenen else "LOW")

    return temiz_metin, {
        "file_validated": True,  # buraya gelindiyse dosya doğrulamasını geçti
        "injection_detected": injection_var,
        "injection_patterns": tehditler,
        "pii_masked": pii_sayim,
        "risk_level": risk,
        "notes": notlar or ["Güvenlik taramasında bulgu yok."],
    }


def _rapor_getir_veya_404(report_id: str) -> Dict[str, Any]:
    """Raporu veritabanından getirir; yoksa açıklayıcı 404 üretir."""
    kayit = db.get_report(report_id)
    if not kayit:
        raise HTTPException(
            status_code=404,
            detail=(
                f"'{report_id}' kimlikli rapor bulunamadı. "
                "Önce POST /api/reports/upload ile rapor yükleyin."
            ),
        )
    return kayit


def _benzerlik_korpusu(haric_tut: Optional[str] = None) -> List[Dict[str, Any]]:
    """Benzerlik/intihal karşılaştırması için mevcut raporların metinlerini toplar."""
    korpus: List[Dict[str, Any]] = []
    for kayit in db.get_all_reports():
        if haric_tut and kayit.get("report_id") == haric_tut:
            continue
        metin = kayit.get("report_text") or ""
        if metin:
            korpus.append({
                "report_id": kayit.get("report_id"),
                "project_title": kayit.get("project_name") or "İsimsiz Proje",
                "text": metin,
            })
    return korpus


# ==========================================
# AKIŞ 01: YARIŞMA YÖNETİCİSİ ENDPOINT'LERİ
# ==========================================

@router.post("/reports/upload", response_model=ReportUploadResponse)
async def upload_report(
    file: UploadFile = File(...),
    category: str = Form("Yapay Zekâ ve Otonom Sistemler"),
    project_name: str = Form("İsimsiz Proje"),
    stage: Optional[str] = Form(
        None,
        description="Rapor aşaması: ÖTR / KTR / FTR (boşsa GENEL şartname kullanılır)",
    ),
):
    """
    [Akış 01 - Yönetici] Raporu güvenlik taramasından geçirir, kalıcı olarak
    saklar, AI 4. Göz ön değerlendirmesini çalıştırır ve veritabanına kaydeder.

    ÇOK AŞAMALI: `stage` (ÖTR/KTR/FTR) verildiğinde AI değerlendirmesi o aşamanın
    şartname kriterleriyle yapılır.
    """
    content = await file.read()
    filename = file.filename or "rapor.pdf"

    # --- 1. DOSYA GÜVENLİĞİ (diske ve LLM'e gitmeden ÖNCE) ---
    # Uzantı + PDF magic bytes + boyut sınırı kontrolü.
    guvenli_mi, guvenlik_mesaji = SecurityGuard.validate_file_safety(filename, content)
    if not guvenli_mi:
        raise HTTPException(status_code=400, detail=guvenlik_mesaji)

    report_id = f"rep_{uuid.uuid4().hex[:8]}"

    # --- 2. METİN ÇIKARMA (Birhan / Issue #1) ---
    try:
        pdf_sonucu = load_pdf(content, filename=filename)
        rapor_metni = (pdf_sonucu.get("raw_text") or "").strip()
        if not pdf_sonucu.get("success", True):
            print(f"[UYARI] PDF ayrıştırılamadı: {pdf_sonucu.get('error')}")
            rapor_metni = ""
    except Exception as e:
        print(f"[UYARI] PDF ayrıştırma hatası ({filename}): {type(e).__name__}: {e}")
        rapor_metni = ""

    if not rapor_metni:
        rapor_metni = f"{_METIN_YOK_NOTU}\nDosya: {filename}\nKategori: {category}"

    # --- 3. GÜVENLİK TARAMASI + KVKK MASKELEME ---
    llm_metni, guvenlik_sonucu = _guvenlik_taramasi(rapor_metni)

    # --- 4. KALICI DEPOLAMA (Cloudflare R2, yapılandırılmamışsa yerel disk) ---
    depolama = storage.upload_file_bytes(content, f"{report_id}_{filename}")
    if depolama.get("status") == "ERROR":
        print(f"[UYARI] Depolama başarısız: {depolama.get('error')}")

    # --- 5. 6 MVP KONTROLÜ (dil, şablon, başlık, kategori, benzerlik) ---
    # Her kontrol hata izolasyonu altında çalışır; biri patlarsa yükleme sürer.
    # Şablon kuralları (sayfa/bölüm) (kategori, aşama) rubriğinden gelir.
    kontroller = run_all_checks(
        file_bytes=content,
        report_text=llm_metni,
        category_name=category,
        stage=stage,
        report_id=report_id,
        corpus=_benzerlik_korpusu(haric_tut=report_id),
    )

    # --- 6. AI 4. GÖZ DEĞERLENDİRMESİ (temizlenmiş metinle, aşamaya özel rubric) ---
    ai_eval = evaluate_report_with_ai(llm_metni, category_name=category, stage=stage)

    # --- 7. VERİTABANINA KALICI KAYIT ---
    depolama_backend = "R2" if depolama.get("status") == "SUCCESS" else "LOCAL"
    db.save_report({
        "report_id": report_id,
        "filename": filename,
        "project_name": project_name,
        "category": category,
        "stage": stage,
        "r2_url": depolama.get("r2_url") or depolama.get("url", ""),
        "status": "READY_FOR_REFEREE",
        "ai_score": ai_eval.get("total_score", 0.0),
        "ai_data": ai_eval,
        "report_text": llm_metni,
        "security": guvenlik_sonucu,
        "checks": kontroller,
    })

    return ReportUploadResponse(
        report_id=report_id,
        filename=filename,
        status="PROCESSED",
        message=(
            "Rapor başarıyla yüklendi; güvenlik taraması, kalıcı kayıt ve "
            "AI 4. göz ön değerlendirmesi tamamlandı."
        ),
        timestamp=datetime.datetime.now().isoformat(),
        storage_backend=depolama_backend,
        security_risk_level=guvenlik_sonucu["risk_level"],
    )



# ==========================================
# AKIŞ 02: HAKEM / DEĞERLENDİRİCİ ENDPOINT'LERİ
# ==========================================

def _kontrolleri_yeniden_calistir(rapor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kontrolleri kayıtlı metinden yeniden çalıştırır (eski raporlar veya
    ?refresh=true için). PDF baytları saklanmadığından şablon kontrolü boş baytla
    çalışır; hata izolasyonu devrede olduğundan güvenli yedeğe düşer.
    """
    report_id = rapor.get("report_id")
    return run_all_checks(
        file_bytes=b"",
        report_text=rapor.get("report_text") or "",
        category_name=rapor.get("category") or "Genel",
        stage=rapor.get("stage"),
        report_id=report_id,
        corpus=_benzerlik_korpusu(haric_tut=report_id),
    )


@router.get("/reports/{report_id}/analysis", response_model=ComprehensiveReportAnalysisResponse)
async def get_comprehensive_analysis(
    report_id: str,
    refresh: bool = Query(
        False,
        description="Kontrolleri yeniden çalıştır (ekip modülleri güncellendikten sonra)"
    ),
):
    """
    [Akış 02 - Hakem] Raporun 6 MVP kontrolünü, güvenlik bulgularını ve
    AI 4. Göz kriter değerlendirmesini tek ekranda döner.

    Kontroller yükleme anında çalıştırılıp veritabanına yazılır; burada okunur.
    `?refresh=true` ile metinden yeniden çalıştırılır. Şablon sayfa sınırı ve
    zorunlu bölüm seti (kategori, aşama) rubriğinden gelir.
    """
    rapor = _rapor_getir_veya_404(report_id)
    ai_eval = rapor.get("ai_data") or {}
    guvenlik = rapor.get("security") or {}
    kontroller = rapor.get("checks") or {}

    # Eski raporda kontrol yoksa veya refresh istendiyse yeniden çalıştır.
    if refresh or not kontroller.get("language_check"):
        kontroller = _kontrolleri_yeniden_calistir(rapor)
        db.save_checks(report_id, kontroller)

    return ComprehensiveReportAnalysisResponse(
        report_id=report_id,
        filename=rapor.get("filename", "rapor.pdf"),
        category=rapor.get("category", "Genel Kategori"),
        overall_status=rapor.get("status", "READY_FOR_REFEREE"),
        language_check=kontroller["language_check"],
        template_check=kontroller["template_check"],
        section_check=kontroller["section_check"],
        category_check=kontroller["category_check"],
        similarity_check=kontroller["similarity_check"],
        check_warnings=kontroller.get("check_warnings", []),
        security_check={
            "file_validated": guvenlik.get("file_validated", True),
            "injection_detected": guvenlik.get("injection_detected", False),
            "injection_patterns": guvenlik.get("injection_patterns", []),
            "pii_masked": guvenlik.get("pii_masked", {}),
            "risk_level": guvenlik.get("risk_level", "LOW"),
            "notes": guvenlik.get("notes", []),
        },
        ai_evaluation={
            "total_ai_score": ai_eval.get("total_score", 0.0),
            "executive_summary": ai_eval.get("executive_summary", "Değerlendirme özeti bulunamadı."),
            "referee_recommendation": ai_eval.get("referee_recommendation", "REVİZYON"),
            "confidence_score": ai_eval.get("confidence_score", 0.90),
            "criteria": [
                {
                    "criterion_id": c.get("criterion_id", "c"),
                    "criterion_name": c.get("criterion_name", "Kriter"),
                    "ai_score": c.get("score", 0.0),
                    "max_score": c.get("max_score", 20.0),
                    "reasoning": c.get("reasoning", "Açıklama yok."),
                    "strengths": c.get("strengths", []),
                    "weaknesses": c.get("weaknesses", []),
                }
                for c in ai_eval.get("criteria", [])
            ],
        },
    )


@router.post("/referee/evaluate", response_model=RefereeDecisionResponse)
async def submit_referee_evaluation(decision: RefereeEvaluationRequest):
    """
    [Akış 02 - Hakem] Hakemin nihai kararını, puanını ve notlarını KALICI kaydeder.
    """
    rapor = _rapor_getir_veya_404(decision.report_id)

    # Hakem notu serbest metindir ve sonradan arayüzde gösterilir:
    # XSS'e karşı depolamadan önce temizlenir.
    temiz_not = SecurityGuard.sanitize_input(decision.referee_notes or "") or None

    guncellendi = db.update_referee_decision(
        report_id=decision.report_id,
        referee_id=decision.referee_id,
        referee_score=decision.final_score,
        decision=decision.decision,
        referee_notes=temiz_not,
    )
    if not guncellendi:
        raise HTTPException(status_code=500, detail="Hakem kararı veritabanına yazılamadı.")

    # KALİBRASYON: AI ön puanı ile hakem puanı arasındaki fark, panodaki
    # 'referee_trigger_threshold' değerini aşarsa mesaja uyarı eklenir.
    mesaj = f"Rapor {decision.report_id} için hakem değerlendirmesi kalıcı olarak kaydedildi."
    try:
        from src.utils.calibration import get_threshold
        ai_puan = float((rapor.get("ai_data") or {}).get("total_score", rapor.get("ai_score") or 0.0))
        esik = get_threshold("referee_trigger_threshold", 10.0)
        fark = abs(float(decision.final_score) - ai_puan)
        if fark > esik:
            mesaj += (
                f" ⚠ Kalibrasyon uyarısı: hakem puanı ({decision.final_score:.0f}) ile "
                f"AI ön puanı ({ai_puan:.0f}) arasındaki fark {fark:.0f}, eşiği ({esik:.0f}) aşıyor; "
                "değerlendirme gözden geçirilebilir."
            )
    except Exception as e:
        print(f"[KALİBRASYON UYARI] Hakem-AI farkı hesaplanamadı: {type(e).__name__}: {e}")

    return RefereeDecisionResponse(
        report_id=decision.report_id,
        referee_id=decision.referee_id,
        status="COMPLETED",
        final_score=decision.final_score,
        decision=decision.decision,
        message=mesaj,
    )


@router.post("/referee/chat", response_model=RefereeChatResponse)
async def referee_interactive_chat(chat_req: RefereeChatRequest):
    """
    [Hakem Asistanı] Hakemin rapor hakkında AI'ya canlı soru sormasını sağlar.
    Rapor metni veritabanından okunur (sunucu yeniden başlasa da çalışır).
    """
    from src.evaluation.chat_assistant import ask_referee_chat

    rapor = _rapor_getir_veya_404(chat_req.report_id)
    rapor_metni = rapor.get("report_text") or _METIN_YOK_NOTU

    # Hakemin sorusu da prompta giriyor: injection'a karşı temizlenir.
    temiz_soru, _ = SecurityGuard.neutralize_prompt_injection(chat_req.question)

    chat_res = ask_referee_chat(rapor_metni, temiz_soru, chat_req.chat_history)
    return RefereeChatResponse(
        report_id=chat_req.report_id,
        question=chat_req.question,
        answer=chat_res["answer"],
        status="SUCCESS",
    )


# ==========================================
# AKIŞ 03: YARIŞMACI GERİ BİLDİRİM ENDPOINT'İ
# ==========================================

@router.get("/contestant/feedback/{report_id}", response_model=ContestantFeedbackResponse)
async def get_contestant_feedback(report_id: str):
    """
    [Akış 03 - Yarışmacı] Güçlü yönleri, eksikleri ve somut gelişim yol haritasını döner.
    Üretilen karne veritabanına kaydedilir; her istekte yeniden üretilmez.
    """
    rapor = _rapor_getir_veya_404(report_id)

    kayitli_karne = rapor.get("feedback") or {}
    if kayitli_karne.get("actionable_roadmap"):
        karne = kayitli_karne
    else:
        degerlendirme = dict(rapor.get("ai_data") or {})

        # Hakem nihai puanını verdiyse karne AI ön puanına göre DEĞİL,
        # hakemin puanına göre üretilir. Aksi hâlde hakemin 88 verdiği bir
        # proje, AI'ın 58'i yüzünden "revizyon" bandında karne alıyordu.
        hakem_puani = rapor.get("referee_score")
        if hakem_puani is not None:
            degerlendirme["total_score"] = float(hakem_puani)

        karne = generate_contestant_feedback(report_id, degerlendirme)
        db.save_feedback(report_id, karne)

    return ContestantFeedbackResponse(
        report_id=report_id,
        total_score=karne["total_score"],
        status=karne["status"],
        message=karne["message"],
        strengths=karne["strengths"],
        areas_to_improve=karne["areas_to_improve"],
        actionable_roadmap=karne["actionable_roadmap"],
        pedagogical_advice=karne["pedagogical_advice"],
    )


@router.get("/contestant/feedback/{report_id}/pdf")
async def download_contestant_feedback_pdf(report_id: str):
    """
    [Akış 03 - Yarışmacı / Jüri] Yarışmacı gelişim karnesini resmi formatta,
    renkli ve grafiksel bir PDF belgesi olarak indirir.
    """
    rapor = _rapor_getir_veya_404(report_id)
    
    # Karne verisi yoksa veya eskiyse üret
    kayitli_karne = rapor.get("feedback") or {}
    if kayitli_karne.get("actionable_roadmap"):
        karne = kayitli_karne
    else:
        degerlendirme = dict(rapor.get("ai_data") or {})
        hakem_puani = rapor.get("referee_score")
        if hakem_puani is not None:
            degerlendirme["total_score"] = float(hakem_puani)
        karne = generate_contestant_feedback(report_id, degerlendirme)
        db.save_feedback(report_id, karne)

    pdf_bytes = generate_feedback_pdf(rapor, karne)
    filename = f"TEKNOFEST_Gelisim_Karnesi_{report_id}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ==========================================
# DEĞERLENDİRME YÖNETİCİSİ / DASHBOARD METRİKLERİ
# ==========================================

@router.get("/admin/metrics", response_model=AdminMetricsResponse)
async def get_admin_dashboard_metrics(
    user: AuthUser = Depends(require_roles([UserRole.ADMIN, UserRole.HEAD_REFEREE]))
):
    """
    [Değerlendirme Yöneticisi & Baş Hakem] Değerlendirme akışının canlı özeti.
    Değerler veritabanından dinamik hesaplanır.
    """
    return AdminMetricsResponse(**db.get_metrics())


# ==========================================
# YARIŞMA ŞARTNAME & RUBRİC YÖNETİMİ (ADMİN)
# ==========================================

@router.post("/admin/rubrics", response_model=CompetitionRubricResponse)
async def create_or_update_competition_rubric(
    rubric_req: CompetitionRubricRequest,
    user: AuthUser = Depends(require_roles([UserRole.ADMIN]))
):
    """
    [Değerlendirme Yöneticisi] 60+ TEKNOFEST yarışması için özel şartname kriterlerini,
    ağırlıklarını, maksimum puanlarını ve zorunlu başlıklarını sisteme kaydeder.
    """
    from src.evaluation.rubric import normalize_stage, stage_display_name

    stage = normalize_stage(rubric_req.stage)
    rubric_data = {
        "category_name": rubric_req.category_name.strip(),
        "stage": stage,
        "description": rubric_req.description or "",
        "criteria": [c.model_dump() for c in rubric_req.criteria],
        "required_sections": rubric_req.required_sections or {},
        "max_pages": rubric_req.max_pages or 15,
    }

    db.save_rubric(rubric_data)
    kayitli = db.get_rubric_by_category(rubric_req.category_name, stage)
    if not kayitli:
        raise HTTPException(status_code=500, detail="Şartname kriterleri veritabanına kaydedilemedi.")

    asama_etiket = f" ({stage_display_name(stage)})" if stage != "GENEL" else ""
    return CompetitionRubricResponse(
        category_id=kayitli["category_id"],
        category_name=kayitli["category_name"],
        stage=kayitli.get("stage", "GENEL"),
        description=kayitli["description"],
        criteria=kayitli["criteria"],
        required_sections=kayitli["required_sections"],
        max_pages=kayitli["max_pages"],
        created_at=kayitli["created_at"],
        message=f"'{rubric_req.category_name}'{asama_etiket} yarışma şartname kriterleri başarıyla kaydedildi.",
    )


@router.get("/admin/rubrics", response_model=List[CompetitionRubricResponse])
async def list_all_competition_rubrics():
    """
    [Değerlendirme Yöneticisi] Sistemde tanımlı tüm yarışma şartnamelerini
    (her yarışmanın her aşaması ayrı satır olarak) listeler.
    """
    rubrics = db.get_all_rubrics()
    return [
        CompetitionRubricResponse(
            category_id=r["category_id"],
            category_name=r["category_name"],
            stage=r.get("stage", "GENEL"),
            description=r["description"],
            criteria=r["criteria"],
            required_sections=r["required_sections"],
            max_pages=r["max_pages"],
            created_at=r["created_at"],
            message="Kayıtlı şartname",
        )
        for r in rubrics
    ]


@router.get("/admin/rubrics/{category_name}", response_model=CompetitionRubricResponse)
async def get_competition_rubric(
    category_name: str,
    stage: Optional[str] = Query(
        None, description="Rapor aşaması: ÖTR / KTR / FTR (boşsa GENEL / ilk bulunan)"
    ),
):
    """
    [Değerlendirme Yöneticisi / Arayüz] Belirli bir yarışma+aşama şartname
    kriterlerini döner. Arayüz kriter kartlarını bu yanıttan basar.
    """
    r = db.get_rubric_by_category(category_name, stage)
    if not r:
        raise HTTPException(
            status_code=404,
            detail=f"'{category_name}' ({stage or 'GENEL'}) için özel şartname bulunamadı.",
        )
    return CompetitionRubricResponse(
        category_id=r["category_id"],
        category_name=r["category_name"],
        stage=r.get("stage", "GENEL"),
        description=r["description"],
        criteria=r["criteria"],
        required_sections=r["required_sections"],
        max_pages=r["max_pages"],
        created_at=r["created_at"],
        message="Kayıtlı şartname",
    )


@router.delete("/admin/rubrics/{category_name}")
async def delete_competition_rubric(
    category_name: str,
    stage: Optional[str] = Query(None, description="Silinecek aşama (boşsa GENEL)"),
    user: AuthUser = Depends(require_roles([UserRole.ADMIN])),
):
    """[Değerlendirme Yöneticisi] Bir (yarışma, aşama) şartname tanımını siler."""
    silindi = db.delete_rubric(category_name, stage)
    if not silindi:
        raise HTTPException(
            status_code=404,
            detail=f"'{category_name}' ({stage or 'GENEL'}) için kayıtlı şartname bulunamadı.",
        )
    return {"status": "DELETED", "category_name": category_name, "stage": stage or "GENEL"}


@router.get("/competitions")
async def list_competitions_with_stages():
    """
    [Arayüz] Tanımlı yarışmaları ve HER BİRİNİN KENDİ aşama setini döner.

    TEKNOFEST'te her yarışmanın aşamaları farklıdır (Roket: ÖTR/KTR/AHR;
    Model Uydu: POR/PDR/CDR/QR/FRR/PFR; İHA: PDR/KTR). Arayüz, yarışma
    seçildiğinde aşama açılır menüsünü bu yanıttan doldurur — böylece kullanıcıya
    yalnızca o yarışmanın gerçek aşamaları gösterilir.

    Yanıt:
      [{"category_name": "...", "stages": [{"stage": "OTR", "stage_name": "...",
        "max_pages": 15, "criteria_count": 4}, ...]}]
    """
    from src.evaluation.rubric import stage_display_name

    gruplar: Dict[str, List[Dict[str, Any]]] = {}
    for r in db.get_all_rubrics():
        ad = r["category_name"]
        gruplar.setdefault(ad, []).append({
            "stage": r.get("stage", "GENEL"),
            "stage_name": stage_display_name(r.get("stage", "GENEL")),
            "max_pages": r.get("max_pages"),
            "criteria_count": len(r.get("criteria", [])),
            "section_count": len(r.get("required_sections", {})),
        })
    return {
        "competitions": [
            {"category_name": ad, "stages": asamalar}
            for ad, asamalar in gruplar.items()
        ]
    }


class SartnameExtractRequest(BaseModel):
    category_name: str
    stage: Optional[str] = None
    sartname_text: str
    save: bool = False


@router.post("/admin/rubrics/extract")
async def extract_rubric_from_sartname(
    req: SartnameExtractRequest,
    user: AuthUser = Depends(require_roles([UserRole.ADMIN])),
):
    """
    [Değerlendirme Yöneticisi] Bir şartname METNİNDEN taslak rubric ÇIKARIR.

    LLM anahtarı varsa kaliteli (kriter + ağırlık + bölüm + sayfa sınırı) çıkarım;
    yoksa heuristik taslak döner. `save=true` ise taslağı doğrudan kaydeder,
    aksi hâlde yalnızca döndürür (yönetici gözden geçirip POST /admin/rubrics ile
    kaydeder).
    """
    from src.evaluation.rubric_extractor import extract_rubric_from_text

    if not req.sartname_text or len(req.sartname_text.strip()) < 40:
        raise HTTPException(status_code=400, detail="Şartname metni çok kısa veya boş.")

    taslak = extract_rubric_from_text(req.sartname_text, req.category_name, req.stage)
    if req.save:
        db.save_rubric(taslak)

    return {
        "status": "SAVED" if req.save else "DRAFT",
        "rubric": taslak,
        "not": "LLM anahtarı yoksa çıkarım heuristiktir; kriter ağırlıkları gözden geçirilmelidir.",
    }


# ==========================================
# KALİBRASYON / EŞİK AYARLARI (Mehmet - Admin)
# ==========================================

class CalibrationUpdateRequest(BaseModel):
    """Kalibrasyon eşik güncellemesi için istek gövdesi."""
    updates: Dict[str, float]


@router.get("/admin/calibration")
async def get_calibration_settings(
    user: AuthUser = Depends(require_roles([UserRole.ADMIN])),
):
    """
    [Değerlendirme Yöneticisi] Tüm sistem eşik ve kalibrasyon değerlerini getirir.

    Dönen alanlar:
      - similarity_high_risk_threshold: İntihal yüksek risk eşiği (0-1)
      - similarity_medium_risk_threshold: İntihal orta risk eşiği (0-1)
      - referee_trigger_threshold: AI-Hakem farkı uyarı eşiği (puan)
      - min_section_words: Bölüm minimum kelime sayısı
      - ai_score_offset: AI puan sapma düzeltmesi
      - ai_score_slope: AI puan ölçek çarpanı
      - max_report_pages: Varsayılan max sayfa sınırı
      - feedback_min_score_for_positive: Olumlu karne skoru eşiği
    """
    settings = db.get_all_calibration()
    # Simülasyon metrikleri: mevcut DB raporlarına göre dinamik hesapla
    reports = db.get_all_reports()
    ai_scores = [r.get("ai_score") or 0 for r in reports if r.get("ai_score") is not None]
    ref_scores = [r.get("referee_score") or 0 for r in reports if r.get("referee_score") is not None]

    high_t = db.get_calibration_value("similarity_high_risk_threshold", 0.70)
    ref_t = db.get_calibration_value("referee_trigger_threshold", 10.0)
    offset = db.get_calibration_value("ai_score_offset", 0.0)
    slope = db.get_calibration_value("ai_score_slope", 1.0)

    # Simüle edilmiş kalibre puan (slope + offset)
    kalibre_ai = [(s * slope + offset) for s in ai_scores]

    return {
        "settings": settings,
        "simulasyon": {
            "rapor_sayisi": len(reports),
            "ai_puan_ortalama_ham": round(sum(ai_scores) / len(ai_scores), 2) if ai_scores else 0,
            "ai_puan_ortalama_kalibre": round(sum(kalibre_ai) / len(kalibre_ai), 2) if kalibre_ai else 0,
            "hakem_puan_ortalama": round(sum(ref_scores) / len(ref_scores), 2) if ref_scores else 0,
            "aktif_esikler": {
                "intihal_yuksek_risk": f"%{int(high_t * 100)}",
                "hakem_uyari_farki": ref_t,
                "ai_offset": offset,
                "ai_slope": slope,
            }
        }
    }


@router.post("/admin/calibration")
async def update_calibration_settings(
    req: CalibrationUpdateRequest,
    user: AuthUser = Depends(require_roles([UserRole.ADMIN])),
):
    """
    [Değerlendirme Yöneticisi] Sistem eşiklerini toplu günceller.

    Örnek istek:
        {"updates": {"similarity_high_risk_threshold": 0.75, "ai_score_offset": -2.5}}

    Bu değişiklik anında tüm motoru etkiler — bir sonraki rapor analizinden
    itibaren yeni eşikler kullanılır.
    """
    if not req.updates:
        raise HTTPException(status_code=400, detail="En az bir eşik değeri gönderilmelidir.")

    count = db.set_calibration_bulk(req.updates)
    return {
        "status": "UPDATED",
        "guncellenen_sayi": count,
        "guncellenen_anahtarlar": list(req.updates.keys()),
        "mesaj": f"{count} kalibrasyon eşiği başarıyla güncellendi ve anında aktif oldu.",
    }
