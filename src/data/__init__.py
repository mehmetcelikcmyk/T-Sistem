"""T-Sistem veri katmani.

Streamlit ve FastAPI'nin TEK veri kapisi. UI katmani `sqlite3`, `boto3` veya
D1 REST API'sine dogrudan DOKUNMAZ; her sey buradan gecer.

Kullanim:
    from src.data import repos
    yarismalar = repos().competitions.list(publish_status=PublishStatus.YAYINDA)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .client import (
    ConnectionFailed,
    D1Client,
    DataError,
    NotConfigured,
    QueryFailed,
    get_client,
    reset_client,
)
from .r2 import Keys, R2Client, StorageError, StorageNotConfigured, get_r2, slugify
from .repo.applications import ApplicationRepo, EligibilityReport, days_left, parse_date
from .repo.base import DuplicateRecord, RecordNotFound
from .repo.competitions import CompetitionRepo
from .repo.evaluations import EvaluationRepo
from .repo.reports import ReportRepo
from .repo.teams import TeamRepo
from .repo.users import UserRepo, hash_password, verify_password


@dataclass(frozen=True)
class Repos:
    users: UserRepo
    competitions: CompetitionRepo
    teams: TeamRepo
    applications: ApplicationRepo
    reports: ReportRepo
    evaluations: EvaluationRepo
    client: D1Client
    storage: R2Client


@lru_cache(maxsize=1)
def repos() -> Repos:
    client = get_client()
    return Repos(
        users=UserRepo(client),
        competitions=CompetitionRepo(client),
        teams=TeamRepo(client),
        applications=ApplicationRepo(client),
        reports=ReportRepo(client),
        evaluations=EvaluationRepo(client),
        client=client,
        storage=get_r2(),
    )


def reset() -> None:
    """Test/CLI icin tum tekil nesneleri sifirlar."""
    repos.cache_clear()
    reset_client()


__all__ = [
    "repos", "reset", "Repos",
    "UserRepo", "CompetitionRepo", "TeamRepo", "ApplicationRepo",
    "ReportRepo", "EvaluationRepo",
    "D1Client", "R2Client", "Keys", "slugify", "get_client", "get_r2",
    "DataError", "ConnectionFailed", "QueryFailed", "NotConfigured",
    "StorageError", "StorageNotConfigured",
    "RecordNotFound", "DuplicateRecord",
    "EligibilityReport", "parse_date", "days_left",
    "hash_password", "verify_password",
]
