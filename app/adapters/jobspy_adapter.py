"""Adapter do `python-jobspy` para a porta `IJobRepository`."""

import asyncio
import logging
import math
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd
from jobspy import scrape_jobs
from jobspy.model import Country

from app.adapters.rate_limit import RandomDelayThrottle
from app.domain.exceptions import JobSourceError
from app.domain.interfaces import IJobRepository
from app.domain.models import (
    JobPosting,
    JobSearchCriteria,
    JobSite,
    SalaryRange,
    WorkMode,
    detect_work_mode,
    normalize_text,
)

logger = logging.getLogger(__name__)

ScrapeFn = Callable[..., pd.DataFrame]


class JobSpyAdapter(IJobRepository):
    """Busca vagas site a site, com delay randômico entre as requisições.

    O `scrape_jobs` do JobSpy dispara todos os sites em paralelo; aqui cada
    site é consultado isoladamente para que o throttle espace as chamadas e
    para que a falha de um site (ex.: 429 do LinkedIn) não derrube os demais.
    """

    def __init__(
        self,
        *,
        throttle: RandomDelayThrottle | None = None,
        linkedin_fetch_description: bool = True,
        scrape_fn: ScrapeFn = scrape_jobs,
    ) -> None:
        self._throttle = throttle or RandomDelayThrottle(2.0, 6.0)
        self._linkedin_fetch_description = linkedin_fetch_description
        self._scrape = scrape_fn

    async def search(self, criteria: JobSearchCriteria) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        failures: dict[JobSite, Exception] = {}

        country = resolve_country(criteria.location)
        for site in criteria.sites:
            try:
                async with self._throttle:
                    frame = await asyncio.to_thread(
                        self._scrape, **self._kwargs(site, criteria, country)
                    )
            except Exception as exc:  # o JobSpy não tem hierarquia de erros própria
                logger.warning("Falha ao buscar vagas em %s: %r", site, exc)
                failures[site] = exc
                continue
            postings = self._to_postings(frame, site)
            if country:
                # o LinkedIn completa a busca com vagas de outros países
                postings = [p for p in postings if _in_country(p.location, country)]
            jobs.extend(postings)

        if failures and len(failures) == len(criteria.sites):
            detail = "; ".join(f"{site}: {exc!r}" for site, exc in failures.items())
            raise JobSourceError(f"Todas as fontes falharam — {detail}")
        return jobs

    def _kwargs(
        self, site: JobSite, criteria: JobSearchCriteria, country: Country | None
    ) -> dict[str, Any]:
        # só o país ("Brasil"): o nome em inglês é o que o LinkedIn reconhece
        location = _country_name(country).title() if country else criteria.location or None
        return {
            "site_name": [site.value],
            "search_term": criteria.search_term,
            "location": location,
            "is_remote": criteria.remote_only,
            "results_wanted": criteria.results_wanted,
            "hours_old": criteria.hours_old,
            "country_indeed": _country_name(country) if country else criteria.country,
            "linkedin_fetch_description": self._linkedin_fetch_description,
            "description_format": "markdown",
            "verbose": 1,  # só avisos e erros (o JobSpy usa handlers próprios)
        }

    @classmethod
    def _to_postings(cls, frame: pd.DataFrame, site: JobSite) -> list[JobPosting]:
        postings = []
        for raw in frame.to_dict("records"):
            row = {key: _clean(value) for key, value in raw.items()}
            try:
                postings.append(cls._to_posting(row, site))
            except (ValueError, TypeError) as exc:
                logger.debug("Vaga descartada (%s): %s", exc, row.get("job_url"))
        return postings

    @staticmethod
    def _to_posting(row: dict[str, Any], site: JobSite) -> JobPosting:
        url = row.get("job_url") or row.get("job_url_direct")
        if not url:
            raise ValueError("vaga sem URL")
        return JobPosting(
            title=str(row.get("title") or ""),
            company=str(row.get("company") or ""),
            url=str(url),
            source=site,
            location=str(row.get("location") or ""),
            description=str(row.get("description") or ""),
            work_mode=_work_mode(row),
            salary=_salary(row),
            date_posted=_date(row.get("date_posted")),
            job_type=row.get("job_type"),
            skills=tuple(s.strip() for s in str(row.get("skills") or "").split(",") if s.strip()),
            external_id=row.get("id"),
        )


# nomes em português que diferem dos do JobSpy (que só conhece os em inglês)
_PT_COUNTRY_NAMES = {
    "brasil": "brazil",
    "alemanha": "germany",
    "espanha": "spain",
    "estados unidos": "usa",
    "eua": "usa",
    "reino unido": "uk",
    "inglaterra": "uk",
    "franca": "france",
    "holanda": "netherlands",
    "paises baixos": "netherlands",
    "italia": "italy",
    "irlanda": "ireland",
    "canada": "canada",
    "mexico": "mexico",
    "japao": "japan",
    "suica": "switzerland",
    "suecia": "sweden",
    "belgica": "belgium",
    "polonia": "poland",
    "dinamarca": "denmark",
    "noruega": "norway",
    "finlandia": "finland",
    "nova zelandia": "new zealand",
    "africa do sul": "south africa",
    "india": "india",
    "colombia": "colombia",
    "uruguai": "uruguay",
}


def resolve_country(location: str) -> Country | None:
    """O país do JobSpy quando a localização é só um país ("Brasil", "Portugal").

    Cidades, estados e códigos ("SP", "PE") não contam: "Recife, PE" não é o Peru.
    """
    name = normalize_text(location).strip(" .")
    name = _PT_COUNTRY_NAMES.get(name, name)
    for country in Country:
        if country in (Country.US_CANADA, Country.WORLDWIDE):
            continue
        if name in country.value[0].split(","):
            return country
    return None


def _country_name(country: Country) -> str:
    return country.value[0].split(",")[0]


def _in_country(location: str, country: Country) -> bool:
    """Descarta só vagas que declaram outro país; sem país no texto, mantém."""
    declared = resolve_country(location.rsplit(",", 1)[-1])
    return declared is None or declared is country


def _clean(value: Any) -> Any:
    """Converte os marcadores de ausência do pandas (NaN, NaT, None) em None."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _work_mode(row: dict[str, Any]) -> WorkMode:
    """Precedência: o que a empresa escreveu no título/local > flags do JobSpy.

    As flags são incompletas (o LinkedIn marca is_remote=False em vagas com
    "Trabalho Remoto" no título) e a descrição não é usada: menções como
    "auxílio home office" gerariam falsos positivos.
    """
    declared = detect_work_mode(f"{row.get('title') or ''} {row.get('location') or ''}")
    if declared is not WorkMode.UNKNOWN:
        return declared
    wfh = detect_work_mode(str(row.get("work_from_home_type") or ""))
    if wfh is not WorkMode.UNKNOWN:
        return wfh
    return WorkMode.REMOTE if row.get("is_remote") is True else WorkMode.UNKNOWN


def _salary(row: dict[str, Any]) -> SalaryRange | None:
    min_amount, max_amount = row.get("min_amount"), row.get("max_amount")
    if min_amount is None and max_amount is None:
        return None
    try:
        return SalaryRange(
            min_amount=float(min_amount) if min_amount is not None else None,
            max_amount=float(max_amount) if max_amount is not None else None,
            currency=row.get("currency") or "BRL",
            interval=row.get("interval") or "monthly",
        )
    except ValueError:
        return None  # faixa inconsistente (min > max): melhor sem salário que salário errado


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
