"""
T-Sistem — Ana Uygulama Giriş Noktası

Çalıştırma (ikisi de geçerli):
    uvicorn src.main:app --reload        # proje kökünden (önerilen)
    python src/main.py                   # doğrudan script olarak
"""
import os
import sys

# --- Yol bootstrap ---
# 'python src/main.py' ile çalıştırıldığında sys.path[0] = src/ olur ve
# 'from src.api.routes import ...' satırı ModuleNotFoundError verirdi.
# Proje kökünü yola ekleyerek her iki çalıştırma biçimini de destekliyoruz.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.routes import router as api_router
from src.api.ui_adapter import ui_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama yaşam döngüsü. Açılışta data/rubrics/*.json yarışma/aşama
    şartnamelerini veritabanına yükler (overwrite=False: yöneticinin API
    düzenlemeleri korunur, yalnızca eksik tanımlar eklenir). Seed başarısız olsa
    bile sistem varsayılan rubric'le çalışmaya devam eder.
    """
    try:
        from src.evaluation.rubric_seed import seed_rubrics_from_disk
        seed_rubrics_from_disk(overwrite=False)
    except Exception as e:
        print(f"[BAŞLANGIÇ UYARI] Rubric seed atlandı: {type(e).__name__}: {e}")
    yield


app = FastAPI(
    title="T-Sistem API — TEKNOFEST Yapay Zekâ Destekli Değerlendirme Sistemi",
    description="T3 Vakfı Bursiyer Yapay Zekâ Creathonu Problem 4 Hakem Karar Destek ve Değerlendirme Platformu",
    version="1.0.0",
    lifespan=lifespan,
)

@app.post("/api/ext/activate", include_in_schema=False)
async def extension_activate():
    """Tarayıcı eklentilerinin (Swagger/API eklentileri) otomatik ping isteklerini karşılar."""
    return {"status": "ok"}


# ==========================================
# CORS YAPILANDIRMASI
# ==========================================
# NOT: allow_origins=["*"] ile allow_credentials=True birlikte kullanılamaz
# (CORS spesifikasyonu gereği tarayıcı isteği reddeder). Bu yüzden origin
# listesi ortam değişkeninden okunur; joker kullanılırsa credentials kapatılır.
_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "*")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_allow_credentials = "*" not in _allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# GLOBAL HATA YAKALAMA (Issue #4 - Adım 3)
# ==========================================

# Pydantic hata tiplerinin Türkçe karşılıkları
_TR_ERROR_MESSAGES = {
    "missing": "Bu alan zorunludur.",
    "string_type": "Bu alan metin (yazı) tipinde olmalıdır.",
    "int_type": "Bu alan tam sayı olmalıdır.",
    "int_parsing": "Bu alan geçerli bir tam sayı olmalıdır.",
    "float_type": "Bu alan sayısal bir değer olmalıdır.",
    "float_parsing": "Bu alan geçerli bir sayı olmalıdır.",
    "bool_type": "Bu alan doğru/yanlış (true/false) olmalıdır.",
    "list_type": "Bu alan bir liste olmalıdır.",
    "dict_type": "Bu alan bir nesne (obje) olmalıdır.",
    "less_than_equal": "Değer en fazla {le} olabilir.",
    "greater_than_equal": "Değer en az {ge} olmalıdır.",
    "less_than": "Değer {lt} değerinden küçük olmalıdır.",
    "greater_than": "Değer {gt} değerinden büyük olmalıdır.",
    "string_too_short": "Bu alan en az {min_length} karakter olmalıdır.",
    "string_too_long": "Bu alan en fazla {max_length} karakter olabilir.",
    "enum": "Geçersiz seçim. İzin verilen değerler: {expected}",
    "json_invalid": "Gönderilen veri geçerli bir JSON değil.",
    "value_error": "Geçersiz değer.",
}


def _turkish_message(err: dict) -> str:
    """Pydantic hata sözlüğünü anlaşılır bir Türkçe mesaja çevirir."""
    template = _TR_ERROR_MESSAGES.get(err.get("type", ""))
    if not template:
        return f"Geçersiz veri: {err.get('msg', 'bilinmeyen doğrulama hatası')}"
    try:
        return template.format(**(err.get("ctx") or {}))
    except (KeyError, IndexError):
        return template


def _field_path(err: dict) -> str:
    """Hatanın hangi alanda olduğunu okunabilir biçimde döndürür."""
    parts = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
    return ".".join(parts) or "istek gövdesi"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic doğrulama hatalarını anlaşılır Türkçe mesajlarla döndürür."""
    hatalar = [
        {
            "alan": _field_path(err),
            "mesaj": _turkish_message(err),
            "hata_tipi": err.get("type"),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "basarili": False,
            "hata_kodu": "DOGRULAMA_HATASI",
            "mesaj": "Gönderdiğiniz veriler doğrulanamadı. Lütfen aşağıdaki alanları kontrol edin.",
            "detaylar": hatalar,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP hatalarını tutarlı bir Türkçe zarf içinde döndürür."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "basarili": False,
            "hata_kodu": f"HTTP_{exc.status_code}",
            "mesaj": exc.detail if isinstance(exc.detail, str) else "İstek işlenemedi.",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Beklenmeyen tüm hataları yakalar; istemciye teknik ayrıntı sızdırmadan
    Türkçe bir mesaj döner, ayrıntıyı sunucu loglarına yazar.
    """
    print(f"[SUNUCU HATASI] {request.method} {request.url.path} -> {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "basarili": False,
            "hata_kodu": "SUNUCU_HATASI",
            "mesaj": "Sunucuda beklenmeyen bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
        },
    )


# API ve UI Adapter router'larını ekle
app.include_router(api_router)
app.include_router(ui_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "project": "T-Sistem",
        "competition": "T3 Vakfi Yapay Zeka Creathonu",
        "problem": "Problem 4 - TEKNOFEST YZ Destekli Degerlendirme Sistemi",
        "team": ["Mehmet Celik", "Birhan", "Emre"],
        "docs_url": "/docs"
    }


@app.get("/health")
async def health():
    """Sistem ayakta mı kontrolü (izleme ve demo öncesi hızlı doğrulama için)."""
    from src.utils.key_manager import key_manager
    return {
        "status": "ok",
        "llm_key_pool_size": len(key_manager.keys),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


if __name__ == "__main__":
    import uvicorn
    print("🚀 T-Sistem sunucusu başlatılıyor: http://localhost:8000")
    print("📚 API Swagger Dokümantasyonu: http://localhost:8000/docs")
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
