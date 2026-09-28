"""Jinja2: diretório de templates e filtros de apresentação."""

from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.templating import Jinja2Templates

from app.domain.models import JobSite, MatchVerdict, OutreachChannel, OutreachLanguage, WorkMode

TEMPLATES_DIR = Path(__file__).parent / "templates"

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


def br_datetime(value: datetime | None) -> str:
    return value.astimezone().strftime("%d/%m/%Y %H:%M") if value else ""


def safe_url(url: str) -> str:
    """Só http(s): URLs vêm de sites de terceiros e `javascript:` executaria no clique."""
    return url if urlsplit(url).scheme in {"http", "https"} else "#"


def br_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def money(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:,.0f}".replace(",", ".")


def create_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env.filters.update(
        safe_url=safe_url, br_date=br_date, br_datetime=br_datetime, money=money
    )
    templates.env.globals.update(
        work_mode_label=_WORK_MODE_LABELS.get,
        site_label=_SITE_LABELS.get,
        verdict_label=_VERDICT_LABELS.get,
        channel_label=_CHANNEL_LABELS.get,
        language_label=_LANGUAGE_LABELS.get,
        all_sites=list(_SITE_LABELS.items()),
    )
    return templates
