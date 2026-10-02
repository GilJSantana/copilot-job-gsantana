"""Jinja2: diretório de templates e filtros de apresentação."""

import re
from collections.abc import Callable, Iterable
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.templating import Jinja2Templates

from app.domain.models import JobSite, MatchVerdict, OutreachChannel, OutreachLanguage, WorkMode

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

_WORK_MODE_LABELS = {
    WorkMode.REMOTE: "Remoto",
    WorkMode.HYBRID: "Híbrido",
    WorkMode.ONSITE: "Presencial",
    WorkMode.UNKNOWN: "Modelo não informado",
}
_SITE_LABELS = {
    JobSite.LINKEDIN: "LinkedIn",
    JobSite.INDEED: "Indeed",
    JobSite.GLASSDOOR: "Glassdoor",
    JobSite.GOOGLE: "Google",
    JobSite.ZIP_RECRUITER: "ZipRecruiter",
}
_VERDICT_LABELS = {
    MatchVerdict.STRONG: "Match forte",
    MatchVerdict.GOOD: "Bom match",
    MatchVerdict.WEAK: "Match fraco",
    MatchVerdict.POOR: "Pouca aderência",
}


_CHANNEL_LABELS = {
    OutreachChannel.LINKEDIN_CONNECTION: "Convite de conexão (LinkedIn)",
    OutreachChannel.LINKEDIN_MESSAGE: "Mensagem (LinkedIn)",
    OutreachChannel.EMAIL: "E-mail",
}
_LANGUAGE_LABELS = {OutreachLanguage.PT: "Português", OutreachLanguage.EN: "Inglês"}
# valores do JobSpy; desconhecidos aparecem como vieram
_JOB_TYPE_LABELS = {
    "fulltime": "Tempo integral",
    "parttime": "Meio período",
    "contract": "Contrato",
    "internship": "Estágio",
    "temporary": "Temporário",
}
# ordem importa: "Tech Lead Sênior" é liderança, não só senioridade
_SENIORITY_PATTERNS = [
    (re.compile(r"\b(staff|principal|lead|l[íi]der|tech lead)\b", re.I), "Liderança"),
    (re.compile(r"\b(s[êe]nior|sr\.?|senior)\b", re.I), "Sênior"),
    (re.compile(r"\b(pleno|mid[- ]level)\b", re.I), "Pleno"),
    (re.compile(r"\b(j[úu]nior|jr\.?|junior|trainee|est[áa]gi\w*|intern)\b", re.I), "Júnior"),
]


def br_datetime(value: datetime | None) -> str:
    return value.astimezone().strftime("%d/%m/%Y %H:%M") if value else ""


def safe_url(url: str) -> str:
    """Só http(s): URLs vêm de sites de terceiros e `javascript:` executaria no clique."""
    return url if urlsplit(url).scheme in {"http", "https"} else "#"


def br_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def posted_ago(value: date | None, today: date | None = None) -> str:
    """Data de publicação relativa. O JobSpy só traz o dia, então a menor unidade é "hoje"."""
    if value is None:
        return ""
    days = ((today or date.today()) - value).days
    if days <= 0:
        return "hoje"
    if days == 1:
        return "ontem"
    if days < 30:
        return f"há {days} dias"
    return f"em {br_date(value)}"


def seniority_label(title: str) -> str | None:
    """Senioridade inferida do título; None quando o título não diz."""
    return next((label for pattern, label in _SENIORITY_PATTERNS if pattern.search(title)), None)


def job_type_label(value: str) -> str:
    return ", ".join(_JOB_TYPE_LABELS.get(part.strip(), part.strip()) for part in value.split(","))


def money(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:,.0f}".replace(",", ".")


def options(values: Iterable[StrEnum], label: Callable[[StrEnum], str | None]) -> list[tuple[str, str]]:
    """Enum -> pares (valor, rótulo) para o macro `select`."""
    return [(value.value, label(value) or value.value) for value in values]


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env.filters.update(
        safe_url=safe_url,
        br_date=br_date,
        br_datetime=br_datetime,
        money=money,
        posted_ago=posted_ago,
    )
    templates.env.globals.update(
        work_mode_label=_WORK_MODE_LABELS.get,
        site_label=_SITE_LABELS.get,
        verdict_label=_VERDICT_LABELS.get,
        channel_label=_CHANNEL_LABELS.get,
        language_label=_LANGUAGE_LABELS.get,
        seniority_label=seniority_label,
        job_type_label=job_type_label,
        options=options,
        all_sites=list(_SITE_LABELS.items()),
    )
    return templates
