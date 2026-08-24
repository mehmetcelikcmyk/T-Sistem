"""Rapor şablonu kayıt defteri.

Şablonlar koda gömülü DEĞİL, JSON olarak tutulur (data/templates/*.json).
Böylece MVP maddesi "Yarışma Yöneticisi güncel şablonu tanımlar" karşılanır:
yeni bir yarışma şablonu eklemek için kod değişikliği gerekmez.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config import PROJECT_ROOT
from ..models import Language

TEMPLATE_DIR = PROJECT_ROOT / "data" / "templates"


@dataclass(frozen=True)
class SectionSpec:
    key: str
    expected_title: str
    aliases: tuple[str, ...] = ()
    required: bool = True
    min_words: int = 0
    criteria_hint: str = ""
    #: Şablonda başlıkta yazan puan ağırlığı ("OTONOM GÖREVLER (25 Puan)" -> 25).
    #: Uyum skoru bu ağırlıkla hesaplanıyor: 45 puanlık bölümün eksikliği
    #: 2 puanlık bölümün eksikliğiyle aynı ağırlıkta olamaz.
    points: float | None = None
    #: Şablondaki alt kırılımlar — kriter bazlı retrieval'da bölüm filtresi
    subsections: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportTemplate:
    template_id: str
    template_name: str
    expected_language: Language
    sections: tuple[SectionSpec, ...]
    min_pages: int = 0
    max_pages: int = 0
    extra: dict = field(default_factory=dict)

    def section(self, key: str) -> SectionSpec | None:
        for s in self.sections:
            if s.key == key:
                return s
        return None

    @property
    def has_points(self) -> bool:
        """Şablon puan ağırlığı taşıyor mu? (uyum skoru buna göre hesaplanır)"""
        return any(s.points for s in self.sections)

    @property
    def total_points(self) -> float:
        return sum(s.points or 0.0 for s in self.sections)


def _parse(raw: dict) -> ReportTemplate:
    sections = tuple(
        SectionSpec(
            key=s["key"],
            expected_title=s["expected_title"],
            aliases=tuple(s.get("aliases", ())),
            required=bool(s.get("required", True)),
            min_words=int(s.get("min_words", 0)),
            criteria_hint=s.get("criteria_hint", ""),
            points=(float(s["points"]) if s.get("points") is not None else None),
            subsections=tuple(s.get("subsections", ())),
        )
        for s in raw.get("sections", [])
    )
    return ReportTemplate(
        template_id=raw["template_id"],
        template_name=raw["template_name"],
        expected_language=Language(raw.get("expected_language", "tr")),
        sections=sections,
        min_pages=int(raw.get("min_pages", 0)),
        max_pages=int(raw.get("max_pages", 0)),
        extra={k: v for k, v in raw.items() if k not in
               {"template_id", "template_name", "expected_language", "sections",
                "min_pages", "max_pages"}},
    )


@lru_cache(maxsize=32)
def load_template(template_id: str, template_dir: str | None = None) -> ReportTemplate:
    directory = Path(template_dir) if template_dir else TEMPLATE_DIR
    path = directory / f"{template_id}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in directory.glob("*.json"))) or "yok"
        raise FileNotFoundError(
            f"Şablon bulunamadı: {template_id}. Mevcut şablonlar: {available}"
        )
    return _parse(json.loads(path.read_text(encoding="utf-8")))


def list_templates(template_dir: str | None = None) -> list[dict]:
    directory = Path(template_dir) if template_dir else TEMPLATE_DIR
    out = []
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        pts = sum(float(s["points"]) for s in raw.get("sections", [])
                  if s.get("points") is not None)
        out.append(
            {
                "template_id": raw["template_id"],
                "template_name": raw["template_name"],
                "expected_language": raw.get("expected_language", "tr"),
                "section_count": len(raw.get("sections", [])),
                "total_points": round(pts, 1) if pts else None,
            }
        )
    return out
