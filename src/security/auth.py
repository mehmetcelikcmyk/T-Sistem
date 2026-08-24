"""
Rol Bazlı Erişim Kontrolü (RBAC - Role-Based Access Control) Modülü
T3 Vakfı Problem 4 PRD: 4 Temel Rol Yönetimi
- ADMIN (Yarışma Yöneticisi): Tüm raporları, şartnameleri ve metrikleri yönetir.
- HEAD_REFEREE (Baş Hakem): Hakem kararlarını denetler, uyuşmazlıkları çözer.
- FIELD_REFEREE (Alan Hakemi): Atanan raporları puanlar, AI ile soru-cevap yapar.
- CONTESTANT (Yarışmacı): Yalnızca kendi rapor karnesini ve PDF gelişim raporunu görür.
"""
from enum import Enum
from typing import List, Optional
from fastapi import Header, HTTPException, status, Depends
from pydantic import BaseModel

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    HEAD_REFEREE = "HEAD_REFEREE"
    FIELD_REFEREE = "FIELD_REFEREE"
    CONTESTANT = "CONTESTANT"

class AuthUser(BaseModel):
    user_id: str
    name: str
    role: UserRole
    assigned_categories: List[str] = []

def get_current_user(
    x_user_role: Optional[str] = Header("ADMIN", alias="X-User-Role"),
    x_user_id: Optional[str] = Header("usr_default", alias="X-User-Id"),
    x_user_name: Optional[str] = Header("Sistem Kullanıcısı", alias="X-User-Name")
) -> AuthUser:
    """
    HTTP Header'larından kullanıcı kimliğini ve rolünü ayrıştırır.
    Varsayılan olarak geriye dönük uyumluluk için ADMIN kabul eder.
    """
    role_str = (x_user_role or "ADMIN").upper()
    try:
        role = UserRole(role_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Geçersiz kullanıcı rolü: '{x_user_role}'. Geçerli roller: {[r.value for r in UserRole]}"
        )
    
    return AuthUser(
        user_id=x_user_id or "usr_default",
        name=x_user_name or "Kullanıcı",
        role=role
    )

def require_roles(allowed_roles: List[UserRole]):
    """
    Endpoint seviyesinde belirli rollerin erişimini zorunlu kılan bağımlılık (Dependency).
    """
    def _role_checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yetkisiz Erişim! Bu işlem için gerekli roller: {[r.value for r in allowed_roles]}, Mevcut rol: '{user.role.value}'"
            )
        return user
    return _role_checker

