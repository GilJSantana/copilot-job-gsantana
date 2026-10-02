"""Formulários do painel de configurações: validação da entrada e conversão para o domínio.

Os campos de lista chegam como texto (vírgulas ou uma linha por item) para que o
painel funcione com formulários HTML comuns, sem JavaScript.
"""

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.datastructures import FormData

from app.domain.models import (
    PROFILE_BLOCK_TITLE_MAX,
    Certification,
    ContactInfo,
    Education,
    Experience,
    JobSite,
    LLMProviderKind,
    LLMSettings,
    OutreachLanguage,
    ProfileDetails,
    ScraperSettings,
    WorkMode,
)


def split_csv(text: str) -> tuple[str, ...]:
    """'Python, SQL ,, AWS' -> ('Python', 'SQL', 'AWS'), sem repetições."""
    return tuple(dict.fromkeys(item.strip() for item in text.split(",") if item.strip()))


def split_lines(text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def _parts(line: str, expected: int) -> list[str]:
    parts = [part.strip() for part in line.split("|")]
    return parts + [""] * (expected - len(parts))


def form_dict(form: FormData, *list_fields: str) -> dict[str, Any]:
    """FormData -> dict; campos de múltipla escolha (checkboxes) viram listas."""
    data: dict[str, Any] = {key: value for key, value in form.items() if isinstance(value, str)}
    for name in list_fields:
        data[name] = form.getlist(name)
    return data


_LABELS = {
    "full_name": "Nome",
    "headline": "Headline",
    "years_of_experience": "Anos de experiência",
    "title": "Título",
    "company": "Empresa",
    "start": "Início",
    "end": "Término",
    "content": "Descrição",
    "provider": "Provedor",
    "gemini_model": "Modelo do Gemini",
    "ollama_model": "Modelo do Ollama",
    "ollama_base_url": "URL do Ollama",
    "active_sites": "Plataformas ativas",
    "min_delay_seconds": "Delay mínimo",
    "max_delay_seconds": "Delay máximo",
    "max_requests_per_hour": "Requisições por hora",
    "template_text": "Prompt",
}


def describe_errors(exc: ValidationError | ValueError) -> str:
    if not isinstance(exc, ValidationError):
        return str(exc)
    problems = []
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else ""
        # erros de validators personalizados chegam como "Value error, <mensagem>"
        message = str(error["msg"]).removeprefix("Value error, ")
        problems.append(f"{_LABELS[field]}: {message}" if field in _LABELS else message)
    return "; ".join(problems)


# --- Perfil ---------------------------------------------------------------------------


class DetailsForm(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    headline: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=5000)
    years_of_experience: float = Field(default=0.0, ge=0, le=80)
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    target_roles: str = ""
    preferred_locations: str = ""
    preferred_work_modes: list[WorkMode] = []
    languages: str = ""
    # uma por linha: "Grau | Instituição | AAAA-MM | AAAA-MM"
    education: str = ""
    # uma por linha: "Nome | Emissor | Ano"
    certifications: str = ""
    language: OutreachLanguage = OutreachLanguage.PT

    def to_domain(self) -> ProfileDetails:
        """Lança `ValueError` com a linha problemática de formação/certificação."""
        return ProfileDetails(
            full_name=self.full_name.strip(),
            headline=self.headline.strip(),
            summary=self.summary.strip(),
            years_of_experience=self.years_of_experience,
            contact=ContactInfo(
                email=self.email.strip(),
                phone=self.phone.strip(),
                location=self.location.strip(),
                linkedin=self.linkedin.strip(),
                github=self.github.strip(),
                website=self.website.strip(),
            ),
            target_roles=split_csv(self.target_roles),
            preferred_locations=split_csv(self.preferred_locations),
            preferred_work_modes=tuple(dict.fromkeys(self.preferred_work_modes)),
            languages=split_csv(self.languages),
            education=tuple(_education(line) for line in split_lines(self.education)),
            certifications=tuple(_certification(line) for line in split_lines(self.certifications)),
            language=self.language,
        )

    @classmethod
    def values_from(cls, details: ProfileDetails | None) -> dict[str, Any]:
        """Valores para preencher o formulário a partir do que está salvo."""
        if details is None:  # formulário em branco: obrigatórios vazios, demais com o padrão
            return {name: "" if f.is_required() else f.default for name, f in cls.model_fields.items()}
        contact = details.contact
        return {
            "full_name": details.full_name,
            "headline": details.headline,
            "summary": details.summary,
            "years_of_experience": details.years_of_experience,
            "email": contact.email,
            "phone": contact.phone,
            "location": contact.location,
            "linkedin": contact.linkedin,
            "github": contact.github,
            "website": contact.website,
            "target_roles": ", ".join(details.target_roles),
            "preferred_locations": ", ".join(details.preferred_locations),
            "preferred_work_modes": [mode.value for mode in details.preferred_work_modes],
            "languages": ", ".join(details.languages),
            "education": "\n".join(
                " | ".join([e.degree, e.institution, e.start, e.end or ""]).rstrip(" |")
                for e in details.education
            ),
            "certifications": "\n".join(
                " | ".join([c.name, c.issuer, str(c.year or "")]).rstrip(" |")
                for c in details.certifications
            ),
            "language": details.language.value,
        }


def _education(line: str) -> Education:
    degree, institution, start, end = _parts(line, 4)[:4]
    if not degree or not institution or not start:
        raise ValueError(f"Formação '{line}': use 'Grau | Instituição | AAAA-MM | AAAA-MM'")
    return Education(degree=degree, institution=institution, start=start, end=end or None)


def _certification(line: str) -> Certification:
    name, issuer, year = _parts(line, 3)[:3]
    if not name or (year and not re.fullmatch(r"\d{4}", year)):
        raise ValueError(f"Certificação '{line}': use 'Nome | Emissor | Ano'")
    return Certification(name=name, issuer=issuer, year=int(year) if year else None)


class ExperienceForm(BaseModel):
    # só na criação; vazio = gerado a partir da empresa
    id: str = Field(default="", max_length=60)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    # <input type="month"> envia AAAA-MM
    start: str = Field(min_length=1)
    end: str = ""
    highlights: str = ""
    technologies: str = ""
    is_active: bool = False

    def to_domain(self, experience_id: str) -> Experience:
        return Experience(
            id=experience_id,
            title=self.title.strip(),
            company=self.company.strip(),
            location=self.location.strip(),
            start=self.start.strip(),
            end=self.end.strip() or None,
            highlights=split_lines(self.highlights),
            technologies=split_csv(self.technologies),
        )

    @staticmethod
    def values_from(experience: Experience) -> dict[str, Any]:
        return {
            "id": experience.id,
            "title": experience.title,
            "company": experience.company,
            "location": experience.location,
            "start": experience.start,
            "end": experience.end or "",
            "highlights": "\n".join(experience.highlights),
            "technologies": ", ".join(experience.technologies),
        }


class BlockForm(BaseModel):
    title: str = Field(min_length=1, max_length=PROFILE_BLOCK_TITLE_MAX)
    content: str = Field(default="", max_length=5000)
    is_active: bool = False


# --- LLM ------------------------------------------------------------------------------


class LLMForm(BaseModel):
    provider: LLMProviderKind
    # vazio = manter a chave salva
    gemini_api_key: str = ""
    clear_gemini_api_key: bool = False
    gemini_model: str = Field(min_length=1, max_length=100)
    ollama_base_url: str = Field(min_length=1, max_length=300)
    ollama_model: str = Field(min_length=1, max_length=100)

    def to_domain(self, current: LLMSettings) -> LLMSettings:
        if self.clear_gemini_api_key:
            api_key = None
        else:
            api_key = self.gemini_api_key.strip() or current.gemini_api_key
        return LLMSettings(
            provider=self.provider,
            gemini_api_key=api_key,
            gemini_model=self.gemini_model.strip(),
            ollama_base_url=self.ollama_base_url.strip().rstrip("/"),
            ollama_model=self.ollama_model.strip(),
        )


class PromptForm(BaseModel):
    template_text: str = Field(min_length=1, max_length=20000)


def mask_secret(secret: str | None) -> str | None:
    """'AIzaSyD...xyz9' -> '••••xyz9'; nunca devolve a chave inteira ao navegador."""
    if not secret:
        return None
    return "••••" + secret[-4:] if len(secret) > 8 else "••••"


# --- Conectores -----------------------------------------------------------------------


class ScrapersForm(BaseModel):
    active_sites: list[JobSite] = Field(min_length=1)
    min_delay_seconds: float = Field(ge=0, le=600)
    max_delay_seconds: float = Field(ge=0, le=600)
    max_requests_per_hour: int = Field(ge=0, le=10000)
    linkedin_fetch_description: bool = False

    @field_validator("active_sites")
    @classmethod
    def _unique(cls, sites: list[JobSite]) -> list[JobSite]:
        return list(dict.fromkeys(sites))

    def to_domain(self) -> ScraperSettings:
        return ScraperSettings(
            active_sites=tuple(self.active_sites),
            min_delay_seconds=self.min_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
            max_requests_per_hour=self.max_requests_per_hour,
            linkedin_fetch_description=self.linkedin_fetch_description,
        )

    @staticmethod
    def values_from(settings: ScraperSettings) -> dict[str, Any]:
        return {
            "active_sites": [site.value for site in settings.active_sites],
            "min_delay_seconds": settings.min_delay_seconds,
            "max_delay_seconds": settings.max_delay_seconds,
            "max_requests_per_hour": settings.max_requests_per_hour,
            "linkedin_fetch_description": settings.linkedin_fetch_description,
        }
