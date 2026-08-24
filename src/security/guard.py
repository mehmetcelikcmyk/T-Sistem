"""
Siber Güvenlik, Veri Temizleme ve KVKK Anonimleştirme Modülü (T-Sistem Security Guard)
T3 Vakfı & TEKNOFEST Siber Güvenlik Gereksinimlerini Karşılar.
"""
import re
import html
from typing import Dict, Any, List, Tuple

# 1. ZARARLI PROMPT INJECTION KALIPLARI
PROMPT_INJECTION_PATTERNS = [
    r"(?i)\b(ignore previous instructions|önceki talimatları unut|sistemi sıfırla)\b",
    r"(?i)\b(you are now|artık sen|tüm kuralları yok say|tam puan ver)\b",
    r"(?i)\b(system prompt|gizli prompt|jailbreak|give 100 points|give full score)\b",
    r"(?i)\b(bu projeye 100 ver|bu projeyi kabul et|bu rapor(u|a)? kusursuz)\b",
    r"(?i)\b(tam not ver|en yüksek puanı ver|maksimum puan ver|puanı yükselt)\b",
    r"(?i)\b(talimatları görmezden gel|yukarıdaki kuralları unut|yeni talimat)\b",
]

# --- Türkçe karakter normalizasyonu ---
# Yarışmacı "önceki talimatları unut" yerine "onceki talimatlari unut" yazarak
# (Türkçe karaktersiz klavye) savunmayı atlatabiliyordu. Bu yüzden hem metni
# hem kalıpları ASCII'ye indirip İKİNCİ bir tarama daha yapıyoruz.
_TR_ASCII_MAP = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})


def normalize_tr(text: str) -> str:
    """Türkçe karakterleri ASCII karşılıklarına indirir ve küçük harfe çevirir."""
    if not text:
        return ""
    return text.translate(_TR_ASCII_MAP).lower()


# Kalıpların ASCII'ye indirilmiş ikizleri (normalize edilmiş metinde arama için)
PROMPT_INJECTION_PATTERNS_ASCII = [normalize_tr(p) for p in PROMPT_INJECTION_PATTERNS]

# 2. KVKK / KİŞİSEL VERİ TESPİT KALIPLARI
TCKN_PATTERN = r"\b[1-9][0-9]{10}\b"
PHONE_PATTERN = r"\b(?:0\s*5|\+90\s*5)[0-9\s-]{9,13}\b"
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"

# 3. ZARARLI DOSYA VE ÇİFTE UZANTI KALIPLARI
DANGEROUS_EXTENSIONS = [".exe", ".bat", ".sh", ".py", ".js", ".vbs", ".php", ".cmd"]


class SecurityGuard:
    @staticmethod
    def sanitize_input(text: str) -> str:
        """XSS ve HTML/Script enjeksiyonlarını temizler."""
        if not text:
            return ""
        # HTML taglerini zararsız hale getir
        clean_text = html.escape(text)
        return clean_text

    @staticmethod
    def detect_prompt_injection(text: str) -> Tuple[bool, List[str]]:
        """
        Rapor metninde hakemi veya yapay zekâyı manipüle etmeye çalışan
        (Prompt Injection / Jailbreak) gizli komutları yakalar.
        """
        if not text:
            return False, []

        detected_threats: List[str] = []

        # 1. Tarama: metnin orijinal hâli (Türkçe karakterler dâhil)
        for pattern in PROMPT_INJECTION_PATTERNS:
            for m in re.findall(pattern, text):
                hit = m[0] if isinstance(m, tuple) else m
                if hit:
                    detected_threats.append(hit)

        # 2. Tarama: ASCII'ye indirilmiş metin (Türkçe karaktersiz yazımı yakalar)
        normalized = normalize_tr(text)
        for pattern in PROMPT_INJECTION_PATTERNS_ASCII:
            for m in re.findall(pattern, normalized):
                hit = m[0] if isinstance(m, tuple) else m
                if hit:
                    detected_threats.append(hit)

        # Aynı ifadenin iki taramada da yakalanmasını tekilleştir
        unique_threats = list(dict.fromkeys(t.strip() for t in detected_threats if t.strip()))
        return len(unique_threats) > 0, unique_threats

    # Metinden çıkarılan şüpheli talimatın yerine konan işaret.
    INJECTION_PLACEHOLDER = "[ŞÜPHELİ TALİMAT KALDIRILDI]"

    @staticmethod
    def neutralize_prompt_injection(text: str) -> Tuple[str, List[str]]:
        """
        Prompt injection ifadelerini SADECE tespit etmez, metinden ÇIKARIR.

        Rapor metni doğrudan LLM promptuna beslendiği için yalnızca bayrak
        kaldırmak yetmez; manipülasyon ifadeleri değerlendirmeye girmeden önce
        '[ŞÜPHELİ TALİMAT KALDIRILDI]' ile değiştirilir. Hem Türkçe hem ASCII'ye
        indirilmiş (Türkçe karaktersiz atlatma) yazımlar temizlenir.

        Döner: (temizlenmiş_metin, tespit_edilen_ifadeler)
        """
        if not text:
            return "", []

        var_mi, tehditler = SecurityGuard.detect_prompt_injection(text)
        if not var_mi:
            return text, []

        temiz = text
        for pattern in PROMPT_INJECTION_PATTERNS:
            try:
                temiz = re.sub(pattern, SecurityGuard.INJECTION_PLACEHOLDER, temiz)
            except re.error:
                pass
        for pattern in PROMPT_INJECTION_PATTERNS_ASCII:
            try:
                temiz = re.sub(pattern, SecurityGuard.INJECTION_PLACEHOLDER, temiz)
            except re.error:
                pass

        return temiz, tehditler

    @staticmethod
    def anonymize_kvkk_data(text: str) -> Tuple[str, Dict[str, int]]:
        """
        Kişisel Verilerin Korunması Kanunu (KVKK) ve Tarafsız Değerlendirme gereğince
        rapor içerisindeki TC Kimlik, Telefon ve E-posta verilerini maskeler.
        """
        counts = {"tckn": 0, "phone": 0, "email": 0}
        
        # TC Kimlik Maskeleme
        tckn_matches = re.findall(TCKN_PATTERN, text)
        counts["tckn"] = len(tckn_matches)
        masked_text = re.sub(TCKN_PATTERN, "[MASKELENDİ: TCKN]", text)
        
        # Telefon Maskeleme
        phone_matches = re.findall(PHONE_PATTERN, masked_text)
        counts["phone"] = len(phone_matches)
        masked_text = re.sub(PHONE_PATTERN, "[MASKELENDİ: TELEFON]", masked_text)
        
        # E-posta Maskeleme
        email_matches = re.findall(EMAIL_PATTERN, masked_text)
        counts["email"] = len(email_matches)
        masked_text = re.sub(EMAIL_PATTERN, "[MASKELENDİ: E-POSTA]", masked_text)
        
        return masked_text, counts

    @staticmethod
    def validate_file_safety(filename: str, file_bytes: bytes) -> Tuple[bool, str]:
        """
        Yüklenen dosyanın gerçekten geçerli bir PDF olup olmadığını
        ve zararlı uzantı/magic bytes taşımadığını doğrular.
        """
        # 1. Uzantı Kontrolü
        filename_lower = filename.lower()
        if not filename_lower.endswith(".pdf"):
            return False, "Yalnızca .pdf formatında dosyalar kabul edilir."
            
        for bad_ext in DANGEROUS_EXTENSIONS:
            if bad_ext in filename_lower:
                return False, f"Zararlı dosya uzantısı şüphesi: {bad_ext}"

        # 2. Magic Bytes (PDF Başlık Doğrulaması)
        if len(file_bytes) < 4 or not file_bytes.startswith(b"%PDF"):
            return False, "Geçersiz dosya başlığı. Dosya gerçek bir PDF dokümanı değildir (Magic bytes uyumsuz)."

        # 3. Dosya Boyutu Sınırı (En fazla 30 MB)
        max_size = 30 * 1024 * 1024
        if len(file_bytes) > max_size:
            return False, "Dosya boyutu 30 MB sınırını aşamaz."

        return True, "Dosya güvenli."
