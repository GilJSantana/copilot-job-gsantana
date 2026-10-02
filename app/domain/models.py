"""Entidades e value objects do domínio.

O domínio é puro: não depende de FastAPI, SQLAlchemy, JobSpy nem de SDKs
de LLM. Todos os objetos são imutáveis (frozen) para que possam circular
entre camadas sem efeitos colaterais.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field, replace
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


def _fingerprint(obj: object, *, optional: tuple[str, ...] = ()) -> str:
    """Hash estável do conteúdo. Campos `optional` vazios ficam de fora: acrescentar
    um campo novo ao modelo não invalida o que foi calculado antes dele existir."""
    data = {k: v for k, v in asdict(obj).items() if not (k in optional and not v)}
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


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
    # resumo de uma linha de cada experiência ("Cargo — Empresa (2019-01 a atual)")
    experiences: tuple[str, ...] = ()
    # métricas e conquistas cadastradas no painel
    achievements: tuple[str, ...] = ()

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
            "experiences",
            "achievements",
        )

    @property
    def fingerprint(self) -> str:
        """Muda sempre que qualquer campo do perfil muda.

        Gravado junto de cada match: um match feito com outro fingerprint foi
        calculado para um perfil que não existe mais e precisa ser refeito.
        """
        return _fingerprint(self, optional=("experiences", "achievements"))


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


# --- CV Tailor ---------------------------------------------------------------------

_YEAR_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

# Palavras sem conteúdo factual, ignoradas na checagem de lastro (pt e en).
_STOPWORDS = frozenset(
    "a o as os um uma uns umas de da do das dos em no na nos nas por para com sem sob "
    "e ou que se ao aos à às como mais menos muito entre sobre até pelo pela pelos pelas "
    "seu sua seus suas meu minha nosso nossa este esta esse essa isso isto "
    "the an of to in on for with by and or as at from into over via my our its "
    "that this these those is are was were be been".split()
)
# Fração mínima das palavras significativas de um highlight que precisa existir
# no texto original da experiência. Reescritas fiéis ficam perto de 1; frases
# trazidas da descrição da vaga ficam perto de 0.
MIN_HIGHLIGHT_SUPPORT = 0.5


def _stems(text: str) -> set[str]:
    """Radicais aproximados: prefixo de 5 letras une flexões (desenvolvi/desenvolvimento)."""
    words = re.findall(r"[a-z0-9]+", normalize_text(text))
    return {word[:5] for word in words if len(word) > 2 and word not in _STOPWORDS}


def _check_period(start: str, end: str | None, what: str) -> None:
    """Datas no formato AAAA-MM; `end=None` significa "atual"."""
    for value in (start, end):
        if value is not None and not _YEAR_MONTH.match(value):
            raise ValueError(f"{what}: data '{value}' fora do formato AAAA-MM")
    if end is not None and end < start:  # AAAA-MM ordena corretamente como texto
        raise ValueError(f"{what}: término {end} anterior ao início {start}")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContactInfo:
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Experience:
    """Uma experiência do histórico completo. O `id` é estável: as versões
    otimizadas do CV referenciam experiências por ele."""

    id: str
    title: str
    company: str
    start: str
    end: str | None = None
    location: str = ""
    highlights: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("experiência sem id")
        _check_period(self.start, self.end, f"experiência {self.id}")
        _as_tuple(self, "highlights", "technologies")

    @property
    def is_current(self) -> bool:
        return self.end is None


@dataclass(frozen=True, slots=True, kw_only=True)
class Education:
    degree: str
    institution: str
    start: str
    end: str | None = None

    def __post_init__(self) -> None:
        _check_period(self.start, self.end, f"formação {self.degree}")


@dataclass(frozen=True, slots=True, kw_only=True)
class Certification:
    name: str
    issuer: str = ""
    year: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CareerHistory:
    """Histórico profissional completo (profile_data/profile_base.json).

    É a única fonte de fatos para os CVs: cada versão otimizada é um recorte
    e uma reescrita deste histórico, nunca um acréscimo.
    """

    full_name: str
    headline: str
    contact: ContactInfo
    summary: str = ""
    skills: tuple[str, ...] = ()
    experiences: tuple[Experience, ...] = ()
    education: tuple[Education, ...] = ()
    certifications: tuple[Certification, ...] = ()
    languages: tuple[str, ...] = ()
    # idioma em que o histórico está escrito (define quando a checagem de lastro se aplica)
    language: OutreachLanguage = OutreachLanguage.PT
    # métricas e conquistas gerais: podem ser citadas no resumo do CV
    achievements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _as_tuple(
            self, "skills", "experiences", "education", "certifications", "languages", "achievements"
        )
        ids = [experience.id for experience in self.experiences]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de experiência repetidos")

    def experience(self, experience_id: str) -> Experience | None:
        return next((e for e in self.experiences if e.id == experience_id), None)

    @property
    def full_text(self) -> str:
        """Todo o texto factual do histórico (base para checar números citados)."""
        parts = [self.headline, self.summary, *self.achievements]
        for experience in self.experiences:
            parts += [experience.title, *experience.highlights]
        return "\n".join(parts)

    @property
    def known_skills(self) -> frozenset[str]:
        """Skills declaradas ou usadas em alguma experiência (normalizadas)."""
        names = self.skills + tuple(t for e in self.experiences for t in e.technologies)
        return frozenset(normalize_text(name) for name in names)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self, optional=("achievements",))


@dataclass(frozen=True, slots=True, kw_only=True)
class TailoredExperience:
    """Experiência do histórico selecionada para o CV, com os highlights reescritos."""

    experience_id: str
    highlights: tuple[str, ...]

    def __post_init__(self) -> None:
        _as_tuple(self, "highlights")


@dataclass(frozen=True, slots=True, kw_only=True)
class TailoredCV:
    """Conteúdo do CV otimizado para uma vaga (saída do ICVOptimizer)."""

    language: OutreachLanguage
    headline: str
    summary: str
    skills: tuple[str, ...]
    experiences: tuple[TailoredExperience, ...]
    # termos da vaga que o CV passou a cobrir (para exibir ao usuário)
    matched_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.headline.strip() or not self.summary.strip():
            raise ValueError("headline e summary são obrigatórios")
        if not self.experiences:
            raise ValueError("o CV precisa de ao menos uma experiência")
        _as_tuple(self, "skills", "experiences", "matched_keywords")

    def highlight_problem(
        self, highlight: str, original: Experience, history: CareerHistory
    ) -> str | None:
        """Motivo pelo qual o highlight não tem lastro na experiência original (ou None)."""
        source = " ".join((original.title, *original.highlights))
        invented = set(_NUMBER.findall(highlight)) - set(_NUMBER.findall(source))
        if invented:
            return f"números ausentes do histórico: {', '.join(sorted(invented))}"
        # por palavras: só é confiável quando CV e histórico estão no mesmo idioma
        if self.language is history.language:
            words = _stems(highlight)
            support_text = " ".join((source, *original.technologies, *history.skills))
            if words and len(words & _stems(support_text)) / len(words) < MIN_HIGHLIGHT_SUPPORT:
                return f"sem lastro no histórico: \"{highlight}\""
        return None

    def violations_against(self, history: CareerHistory) -> list[str]:
        """Diferenças que indicariam conteúdo inventado em relação ao histórico.

        Regras (vazio = CV íntegro):
          * toda experiência referenciada existe no histórico, sem repetição;
          * toda skill listada foi declarada ou usada em alguma experiência;
          * todo número de um highlight (anos, %, valores, tamanhos de equipe)
            aparece no texto original daquela experiência — o LLM pode
            reescrever, mas não pode criar métricas;
          * no mesmo idioma do histórico, ao menos metade das palavras
            significativas de cada highlight vem daquela experiência — barra
            responsabilidades copiadas da descrição da vaga;
          * todo número do título e do resumo aparece em algum ponto do
            histórico (ex.: "6 anos de experiência" precisa estar no resumo base).
        """
        problems = []
        history_numbers = set(_NUMBER.findall(history.full_text))
        invented = set(_NUMBER.findall(f"{self.headline} {self.summary}")) - history_numbers
        if invented:
            problems.append(f"números ausentes do histórico no resumo: {', '.join(sorted(invented))}")
        seen: set[str] = set()
        for tailored in self.experiences:
            original = history.experience(tailored.experience_id)
            if original is None:
                problems.append(f"experiência inexistente: {tailored.experience_id}")
                continue
            if tailored.experience_id in seen:
                problems.append(f"experiência repetida: {tailored.experience_id}")
            seen.add(tailored.experience_id)
            for highlight in tailored.highlights:
                problem = self.highlight_problem(highlight, original, history)
                if problem:
                    problems.append(f"{tailored.experience_id}: {problem}")
        known = history.known_skills
        unknown = [skill for skill in self.skills if normalize_text(skill) not in known]
        if unknown:
            problems.append(f"skills ausentes do histórico: {', '.join(unknown)}")
        return problems


@dataclass(frozen=True, slots=True, kw_only=True)
class CVVersion:
    """Versão do CV gerada para uma vaga (relacionada a JobPosting por `job_key`).

    Cada geração cria uma versão nova; `pdf_path` é relativo ao armazenamento
    de arquivos (ver IFileStorage), não um caminho absoluto do disco.
    """

    id: str
    job_key: str
    content: TailoredCV
    history_fingerprint: str
    template: str
    pdf_path: str
    provider: str = ""
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("CVVersion sem id")
        if not self.pdf_path.strip():
            raise ValueError("CVVersion sem pdf_path")

    @property
    def download_name(self) -> str:
        """Nome para quem recebe o arquivo, sem o id interno:
        'Ana-Souza_CV_Acme_<id>.pdf' -> 'Ana-Souza_CV_Acme.pdf'."""
        suffix = f"_{self.id}.pdf"
        if self.pdf_path.endswith(suffix):
            return self.pdf_path.removesuffix(suffix) + ".pdf"
        return self.pdf_path

    def is_current_for(self, history: CareerHistory) -> bool:
        """False quando o histórico mudou depois desta versão."""
        return self.history_fingerprint == history.fingerprint


# --- Painel de configurações -------------------------------------------------------

_HTTP_URL = re.compile(r"^https?://\S+$")


class LLMProviderKind(StrEnum):
    GEMINI = "gemini"
    OLLAMA = "ollama"


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMSettings:
    """Provedor de LLM em uso e as credenciais de cada provedor."""

    provider: LLMProviderKind
    gemini_model: str
    ollama_base_url: str
    ollama_model: str
    # repr=False: a chave não aparece em logs nem em mensagens de erro
    gemini_api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.provider is LLMProviderKind.GEMINI and not self.gemini_api_key:
            raise ValueError("informe a API key do Gemini para usá-lo como provedor")
        if not self.gemini_model.strip() or not self.ollama_model.strip():
            raise ValueError("o nome do modelo é obrigatório")
        if not _HTTP_URL.match(self.ollama_base_url):
            raise ValueError("a URL do Ollama deve começar com http:// ou https://")

    @property
    def model(self) -> str:
        return self.gemini_model if self.provider is LLMProviderKind.GEMINI else self.ollama_model


@dataclass(frozen=True, slots=True, kw_only=True)
class ScraperSettings:
    """Ritmo e alcance das buscas nas plataformas de vagas."""

    active_sites: tuple[JobSite, ...]
    min_delay_seconds: float
    max_delay_seconds: float
    # 0 = sem limite
    max_requests_per_hour: int = 0
    linkedin_fetch_description: bool = True

    def __post_init__(self) -> None:
        _as_tuple(self, "active_sites")
        if not self.active_sites:
            raise ValueError("ative ao menos uma plataforma")
        if self.min_delay_seconds < 0 or self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError("o delay exige 0 <= mínimo <= máximo")
        if self.max_requests_per_hour < 0:
            raise ValueError("o limite de requisições por hora não pode ser negativo")


class PromptName(StrEnum):
    """Prompts de sistema editáveis no painel."""

    MATCH_ENGINE = "MATCH_ENGINE_PROMPT"
    CV_TAILOR = "CV_TAILOR_PROMPT"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptTemplate:
    name: PromptName
    template_text: str
    # inativo = o service volta a usar o prompt padrão do código
    is_active: bool = True
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.template_text.strip():
            raise ValueError("o prompt não pode ser vazio")


class ProfileBlockCategory(StrEnum):
    EXPERIENCE = "EXPERIENCE"
    SKILL = "SKILL"
    METRIC = "METRIC"


PROFILE_BLOCK_TITLE_MAX = 100


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileBlock:
    """Bloco do perfil editável no painel (experiência, competência ou conquista).

    O formato de `content` depende da categoria e é responsabilidade do
    ProfileService (ex.: experiências guardam os campos estruturados em JSON).
    """

    category: ProfileBlockCategory
    title: str
    content: str = ""
    is_active: bool = True
    id: int | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("o título é obrigatório")
        if len(self.title) > PROFILE_BLOCK_TITLE_MAX:
            raise ValueError(f"o título passa de {PROFILE_BLOCK_TITLE_MAX} caracteres")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileDetails:
    """Dados do candidato que não são blocos: identificação, contato, formação e preferências."""

    full_name: str
    headline: str
    summary: str = ""
    years_of_experience: float = 0.0
    contact: ContactInfo = ContactInfo()
    target_roles: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    preferred_work_modes: tuple[WorkMode, ...] = ()
    languages: tuple[str, ...] = ()
    education: tuple[Education, ...] = ()
    certifications: tuple[Certification, ...] = ()
    # idioma em que o histórico está escrito
    language: OutreachLanguage = OutreachLanguage.PT

    def __post_init__(self) -> None:
        if not self.full_name.strip() or not self.headline.strip():
            raise ValueError("nome e headline são obrigatórios")
        if self.years_of_experience < 0:
            raise ValueError("anos de experiência não pode ser negativo")
        _as_tuple(
            self,
            "target_roles",
            "preferred_locations",
            "preferred_work_modes",
            "languages",
            "education",
            "certifications",
        )
