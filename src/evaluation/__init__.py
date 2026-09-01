"""T-Sistem degerlendirme katmani.

ADIM 3 (sartname uygunlugu) ve ADIM 4 (rubrik puanlama) BIRBIRINDEN BAGIMSIZ
calisir — kullanicinin #199'daki isteri geregi.
"""

from .engine import (
    ComplianceResult,
    CriterionVerdict,
    ENGINE_VERSION,
    Evidence,
    EvidenceVerifier,
    LLMUnavailable,
    RuleVerdict,
    ScoringResult,
    analyze_compliance,
    page_offsets_from_pdf,
    score_report,
)

__all__ = [
    "analyze_compliance", "score_report", "page_offsets_from_pdf",
    "ComplianceResult", "ScoringResult", "RuleVerdict", "CriterionVerdict",
    "Evidence", "EvidenceVerifier", "LLMUnavailable", "ENGINE_VERSION",
]
