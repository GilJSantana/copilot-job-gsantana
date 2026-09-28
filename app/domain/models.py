"""Entidades e value objects do domínio.

O domínio é puro: não depende de FastAPI, SQLAlchemy, JobSpy nem de SDKs
de LLM. Todos os objetos são imutáveis (frozen) para que possam circular
entre camadas sem efeitos colaterais.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from enum import StrEnum


def normalize_text(value: str) -> str:
    """Casefold, remove acentos e colapsa espaços. Preserva pontuação (C#, Node.js)."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.split())


def _canonical(value: str) -> str:
    """normalize_text + pontuação vira espaço: forma usada para comparar identidades."""
    return " ".join(re.sub(r"[^\w\s]", " ", normalize_text(value)).split())


_COMPANY_SUFFIXES = re.compile(r"(\s(ltda|s a|sa|inc|llc|ltd|eireli|corp|gmbh|plc))+$")


def canonical_company(company: str) -> str:
    """'ACME Ltda.', 'ACME S.A.' e 'Acme' viram 'acme'."""
    canonical = _canonical(company)
    return _COMPANY_SUFFIXES.sub("", canonical) or canonical


def canonical_location(location: str) -> str:
    """Só a cidade: 'São Paulo, SP, BR', 'São Paulo, São Paulo, Brazil' e
    'São Paulo - SP' viram 'sao paulo'. Hífen sem espaços ('Embu-Guaçu') é preservado."""
    return _canonical(re.split(r",|\s[-–]\s", location, maxsplit=1)[0])


def _as_tuple(obj: object, *names: str) -> None:
    """Converte listas recebidas (ex.: de JSON) em tuplas, mantendo a imutabilidade."""
    for name in names:
        object.__setattr__(obj, name, tuple(getattr(obj, name)))


class JobSite(StrEnum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    GOOGLE = "google"
    ZIP_RECRUITER = "zip_recruiter"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class MatchVerdict(StrEnum):
    STRONG = "strong"
    GOOD = "good"
    WEAK = "weak"
    POOR = "poor"

    @classmethod
    def from_score(cls, score: float) -> "MatchVerdict":
        if score >= 80:
            return cls.STRONG
        if score >= 65:
            return cls.GOOD
        if score >= 45:
            return cls.WEAK
        return cls.POOR


# Aplicados sobre _canonical(): sem acentos, minúsculas, pontuação vira espaço
# ("on-site" -> "on site", "Híbrido" -> "hibrido", "100% remoto" -> "100 remoto").
_WORK_MODE_PATTERNS: dict[WorkMode, re.Pattern[str]] = {
    WorkMode.REMOTE: re.compile(r"\b(remot[oa]|remote|home office|anywhere|teletrabalho)\b"),
    WorkMode.HYBRID: re.compile(r"\b(hibrid[oa]|hybrid)\b"),
    WorkMode.ONSITE: re.compile(r"\b(presencial|on site|onsite|in office)\b"),
}


def detect_work_mode(text: str) -> WorkMode:
    """Modo de trabalho declarado explicitamente em um texto curto (título, local).

    Não use com descrições longas: menções como "auxílio home office" ou
    "não é remoto" gerariam falsos positivos. Quando o texto cita mais de um
    modo ("Remoto ou Híbrido"), vale o híbrido; outras combinações são ambíguas.
    """
    canonical = _canonical(text)
    found = {mode for mode, pattern in _WORK_MODE_PATTERNS.items() if pattern.search(canonical)}
    if len(found) == 1:
        return found.pop()
    if WorkMode.HYBRID in found:
        return WorkMode.HYBRID
    return WorkMode.UNKNOWN


# Palavras que não mudam qual vaga é: modo de trabalho, país/região, conectivos
# e marcadores de gênero ("Desenvolvedor(a)" -> "desenvolvedor a").
_TITLE_NOISE = re.compile(
    r"\b(100|remot[oa]|remote|home office|anywhere|teletrabalho|hibrid[oa]|hybrid"
    r"|presencial|on site|onsite|in office|trabalho|modelo|regime|vaga|job"
    r"|brasil|brazil|latam|de|da|do|das|dos|para|em|e|a|o|as|os|the|of|for|and|to|in)\b"
)


def canonical_title(title: str) -> str:
    """Conjunto ordenado das palavras significativas do título.

    'Staff Backend Engineer – Python - Trabalho Remoto' e 'Staff Backend
    Engineer (Python)' viram 'backend engineer python staff'. Senioridade
    ('Senior', 'Pleno', 'II') é preservada: são vagas diferentes.
    """
    canonical = _canonical(title)
    tokens = set(_TITLE_NOISE.sub(" ", canonical).split())
    return " ".join(sorted(tokens)) or canonical


@dataclass(frozen=True, slots=True, kw_only=True)
class SalaryRange:
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "BRL"
    interval: str = "monthly"

    def __post_init__(self) -> None:
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError("min_amount não pode ser maior que max_amount")


@dataclass(frozen=True, slots=True)
class JobListing:
    """Onde uma vaga está publicada: uma mesma vaga pode ter vários anúncios."""

    source: JobSite
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JobPosting:
    """Vaga normalizada, independente da fonte (LinkedIn, Indeed, ...)."""

    title: str
    company: str
    url: str
    source: JobSite
    location: str = ""
    description: str = ""
    work_mode: WorkMode = WorkMode.UNKNOWN
    salary: SalaryRange | None = None
    date_posted: date | None = None
    job_type: str | None = None
    skills: tuple[str, ...] = ()
    external_id: str | None = None
    # anúncios da mesma vaga em outras fontes, descobertos na deduplicação
    other_listings: tuple[JobListing, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title é obrigatório")
        if not self.company.strip():
            raise ValueError("company é obrigatório")
        _as_tuple(self, "skills", "other_listings")

    @property
    def listing(self) -> JobListing:
        return JobListing(self.source, self.url)

    @property
    def all_listings(self) -> tuple[JobListing, ...]:
        """O anúncio principal seguido dos demais."""
        return (self.listing, *self.other_listings)

    @property
    def dedup_key(self) -> str:
        """Identidade lógica da vaga: a mesma vaga publicada em fontes diferentes
        (LinkedIn e Indeed, por exemplo) gera a mesma chave.

        Vagas que se declaram remotas no TÍTULO ignoram o local: empresas
        publicam a mesma vaga remota uma vez por cidade/estado. O `work_mode`
        não entra na regra de propósito: as flags de remoto variam entre sites
        (LinkedIn "desconhecido" x Indeed "remoto" para a mesma vaga), e usá-las
        separaria cópias que hoje são reconhecidas como iguais.

        ATENÇÃO: a chave é persistida. Mudar este algoritmo invalida as chaves
        já gravadas — o teste de regressão com valor fixo existe para isso.
        """
        remote = detect_work_mode(self.title) is WorkMode.REMOTE
        canonical = "|".join(
            (
                canonical_title(self.title),
                canonical_company(self.company),
                "" if remote else canonical_location(self.location),
            )
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def searchable_text(self) -> str:
        return "\n".join((self.title, self.description, " ".join(self.skills)))

    def merged_with(self, other: "JobPosting") -> "JobPosting":
        """Funde uma cópia da mesma vaga vinda de outra fonte (ou de outra busca).

        `self` define a identidade exibida (URL, fonte, título); `other` só
        completa lacunas. Nenhum valor conhecido de `self` é sobrescrito.
        """
        if other.dedup_key != self.dedup_key:
            raise ValueError("só é possível fundir cópias da mesma vaga")
        dates = [d for d in (self.date_posted, other.date_posted) if d is not None]
        return replace(
            self,
            description=max(self.description, other.description, key=len),
            salary=self.salary or other.salary,
            # a data mais antiga é a publicação original; as demais são republicações
            date_posted=min(dates, default=None),
            work_mode=self.work_mode if self.work_mode is not WorkMode.UNKNOWN else other.work_mode,
            job_type=self.job_type or other.job_type,
            skills=tuple(dict.fromkeys(self.skills + other.skills)),
            other_listings=self._merge_listings(other),
        )

    def _merge_listings(self, other: "JobPosting") -> tuple[JobListing, ...]:
        """Anúncios de `other` que ainda não são conhecidos, sem repetir URLs."""
        seen = {self.url}
        merged = []
        for listing in (*self.other_listings, *other.all_listings):
            if listing.url not in seen:
                seen.add(listing.url)
                merged.append(listing)
        return tuple(merged)


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSearchCriteria:
    search_term: str
    location: str = ""
    sites: tuple[JobSite, ...] = (JobSite.LINKEDIN, JobSite.INDEED)
    results_wanted: int = 20
    hours_old: int | None = 72
    remote_only: bool = False
    country: str = "brazil"

    def __post_init__(self) -> None:
        if not self.search_term.strip():
            raise ValueError("search_term é obrigatório")
        if self.results_wanted <= 0:
            raise ValueError("results_wanted deve ser positivo")
        if self.hours_old is not None and self.hours_old <= 0:
            raise ValueError("hours_old deve ser positivo")
        _as_tuple(self, "sites")
        if not self.sites:
            raise ValueError("informe ao menos um site")


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateProfile:
    """Perfil do candidato (carregado de profile_data/profile.json)."""

    full_name: str
    headline: str
    skills: tuple[str, ...]
    summary: str = ""
    years_of_experience: float = 0.0
    target_roles: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    preferred_work_modes: tuple[WorkMode, ...] = ()
    languages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.years_of_experience < 0:
            raise ValueError("years_of_experience não pode ser negativo")
        _as_tuple(
            self,
            "skills",
            "target_roles",
            "preferred_locations",
            "preferred_work_modes",
            "languages",
        )

    @property
    def fingerprint(self) -> str:
        """Muda sempre que qualquer campo do perfil muda.

        Gravado junto de cada match: um match feito com outro fingerprint foi
        calculado para um perfil que não existe mais e precisa ser refeito.
        """
        canonical = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMAssessment:
    """Avaliação semântica devolvida pelo LLM, já validada."""

    score: float
    rationale: str
    strengths: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score deve estar entre 0 e 100")
        _as_tuple(self, "strengths", "gaps")


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchResult:
    """Resultado final do match perfil x vaga."""

    job_key: str
    score: float
    keyword_score: float
    llm_score: float | None
    matched_skills: tuple[str, ...]
    strengths: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    rationale: str = ""
    provider: str = ""
    profile_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in ("score", "keyword_score"):
            if not 0 <= getattr(self, name) <= 100:
                raise ValueError(f"{name} deve estar entre 0 e 100")
        _as_tuple(self, "matched_skills", "strengths", "gaps")

    @property
    def verdict(self) -> MatchVerdict:
        return MatchVerdict.from_score(self.score)

    @property
    def used_llm(self) -> bool:
        return self.llm_score is not None

    def is_current_for(self, profile: CandidateProfile) -> bool:
        return self.profile_fingerprint == profile.fingerprint


class OutreachChannel(StrEnum):
    LINKEDIN_CONNECTION = "linkedin_connection"
    LINKEDIN_MESSAGE = "linkedin_message"
    EMAIL = "email"

    @property
    def max_length(self) -> int:
        """Limite do corpo da mensagem.

        300 é o limite do próprio LinkedIn para a nota do convite; os demais
        são escolhas editoriais: mensagem fria longa não é lida.
        """
        return {
            OutreachChannel.LINKEDIN_CONNECTION: 300,
            OutreachChannel.LINKEDIN_MESSAGE: 1000,
            OutreachChannel.EMAIL: 1500,
        }[self]

    @property
    def requires_subject(self) -> bool:
        return self is OutreachChannel.EMAIL


class OutreachLanguage(StrEnum):
    PT = "pt"
    EN = "en"


@dataclass(frozen=True, slots=True, kw_only=True)
class OutreachMessage:
    """Rascunho de mensagem para recrutador/gestor, gerado para uma vaga."""

    job_key: str
    channel: OutreachChannel
    language: OutreachLanguage
    body: str
    subject: str | None = None
    provider: str = ""
    profile_fingerprint: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.body.strip():
            raise ValueError("body não pode ser vazio")
        if len(self.body) > self.channel.max_length:
            raise ValueError(
                f"body tem {len(self.body)} caracteres; o limite de {self.channel} é "
                f"{self.channel.max_length}"
            )
        if self.channel.requires_subject and not (self.subject and self.subject.strip()):
            raise ValueError(f"{self.channel} exige assunto")
        if not self.channel.requires_subject and self.subject is not None:
            raise ValueError(f"{self.channel} não tem assunto")
