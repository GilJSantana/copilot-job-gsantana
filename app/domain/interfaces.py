"""Portas (interfaces) do domínio.

Services dependem apenas destas abstrações (DIP). Cada interface é pequena e
focada em um único papel (ISP); novos provedores entram como novos adapters
sem alterar os services (OCP).
"""

from abc import ABC, abstractmethod
from typing import Any

from app.domain.models import (
    CandidateProfile,
    CareerHistory,
    CVVersion,
    JobPosting,
    JobSearchCriteria,
    MatchResult,
    OutreachLanguage,
    OutreachMessage,
    ProfileBlock,
    ProfileBlockCategory,
    PromptName,
    PromptTemplate,
    TailoredCV,
)


class IJobRepository(ABC):
    """Fonte de vagas externas (ex.: JobSpyAdapter).

    Controle de rate-limit (delay randômico entre requisições, backoff) é
    responsabilidade da implementação: os services não conhecem esse detalhe.
    """

    @abstractmethod
    async def search(self, criteria: JobSearchCriteria) -> list[JobPosting]:
        """Busca vagas segundo os critérios.

        Deve retornar vagas já normalizadas em `JobPosting` e lançar
        `JobSourceError` em caso de falha da fonte.
        """


class IJobStore(ABC):
    """Persistência das vagas já vistas (ex.: SqlAlchemyJobStore).

    Separada de `IJobRepository` (ISP): buscar vagas na web e guardá-las são
    papéis distintos, com implementações e motivos de mudança diferentes.
    """

    @abstractmethod
    async def save_many(self, jobs: list[JobPosting]) -> set[str]:
        """Insere vagas novas e atualiza as já conhecidas (via `JobPosting.merged_with`).

        Retorna os `dedup_key` das vagas que ainda não existiam.
        """

    @abstractmethod
    async def get(self, dedup_key: str) -> JobPosting | None: ...

    @abstractmethod
    async def list_recent(self, *, limit: int = 50, offset: int = 0) -> list[JobPosting]:
        """Vagas mais recentemente descobertas primeiro."""


class IMatchResultStore(ABC):
    """Persistência dos matches, para não pagar o LLM de novo pela mesma vaga."""

    @abstractmethod
    async def save(self, result: MatchResult) -> None:
        """Grava o match, substituindo um anterior da mesma vaga.

        Lança `JobNotFoundError` se a vaga (`result.job_key`) não estiver armazenada.
        """

    @abstractmethod
    async def get(self, job_key: str) -> MatchResult | None: ...

    @abstractmethod
    async def get_many(self, job_keys: list[str]) -> dict[str, MatchResult]:
        """Matches existentes das vagas pedidas; vagas sem match ficam de fora."""


class IOutreachStore(ABC):
    """Histórico de rascunhos de mensagens por vaga."""

    @abstractmethod
    async def save(self, message: OutreachMessage) -> OutreachMessage:
        """Grava um novo rascunho (nunca substitui os anteriores) e o devolve
        com `created_at` preenchido.

        Lança `JobNotFoundError` se a vaga não estiver armazenada.
        """

    @abstractmethod
    async def list_for_job(self, job_key: str) -> list[OutreachMessage]:
        """Rascunhos da vaga, do mais recente para o mais antigo."""


class IProfileRepository(ABC):
    """Origem do perfil do candidato (ex.: StoredCandidateProfiles, lido do banco)."""

    @abstractmethod
    async def get(self) -> CandidateProfile:
        """Lança `ProfileError` se o perfil não existir ou for inválido."""


class ICareerHistoryRepository(ABC):
    """Origem do histórico profissional completo (ex.: StoredCareerHistories, lido do banco)."""

    @abstractmethod
    async def get(self) -> CareerHistory:
        """Lança `ProfileError` se o histórico não existir ou for inválido."""


class ISystemConfigStore(ABC):
    """Parâmetros do sistema como pares chave/valor (tabela system_configs).

    Os valores são texto: quem lê e grava cada chave decide o formato (SRP).
    """

    @abstractmethod
    async def get_many(self, prefix: str) -> dict[str, str]:
        """Pares cuja chave começa com `prefix` (ex.: "llm.")."""

    @abstractmethod
    async def set_many(self, values: dict[str, str], descriptions: dict[str, str] | None = None) -> None:
        """Grava (insere ou substitui) todos os pares numa única transação."""


class IProfileBlockStore(ABC):
    """Blocos do perfil (tabela profile_core)."""

    @abstractmethod
    async def list_all(self, category: ProfileBlockCategory | None = None) -> list[ProfileBlock]:
        """Blocos na ordem de cadastro, opcionalmente só de uma categoria."""

    @abstractmethod
    async def get(self, block_id: int) -> ProfileBlock | None: ...

    @abstractmethod
    async def save(self, block: ProfileBlock) -> ProfileBlock:
        """Insere (`id=None`) ou atualiza o bloco e o devolve com `id` e `updated_at`.

        Lança `ProfileBlockNotFoundError` ao atualizar um bloco que não existe.
        """

    @abstractmethod
    async def delete(self, block_id: int) -> None:
        """Lança `ProfileBlockNotFoundError` se o bloco não existir."""

    @abstractmethod
    async def add_many(self, blocks: list[ProfileBlock]) -> None:
        """Insere vários blocos numa única transação (importação)."""


class IPromptTemplateStore(ABC):
    """Prompts customizados (tabela prompt_templates). Ausente = usar o padrão do código."""

    @abstractmethod
    async def get(self, name: PromptName) -> PromptTemplate | None: ...

    @abstractmethod
    async def save(self, template: PromptTemplate) -> PromptTemplate:
        """Insere ou substitui o prompt e o devolve com `updated_at`."""

    @abstractmethod
    async def delete(self, name: PromptName) -> None:
        """Remove a customização; não falha se ela não existir."""


class ICVVersionStore(ABC):
    """Registro das versões de CV geradas por vaga."""

    @abstractmethod
    async def save(self, version: CVVersion) -> CVVersion:
        """Grava uma nova versão e a devolve com `created_at` preenchido.

        Lança `JobNotFoundError` se a vaga não estiver armazenada.
        """

    @abstractmethod
    async def get(self, version_id: str) -> CVVersion | None: ...

    @abstractmethod
    async def list_for_job(self, job_key: str) -> list[CVVersion]:
        """Versões da vaga, da mais recente para a mais antiga."""

    @abstractmethod
    async def referenced_files(self) -> set[str]:
        """`pdf_path` de todas as versões registradas."""


class IFileStorage(ABC):
    """Armazenamento de arquivos gerados (ex.: LocalFileStorage em output_cvs/)."""

    @abstractmethod
    async def save(self, name: str, data: bytes) -> str:
        """Grava e devolve a referência a ser guardada (relativa ao armazenamento).

        Lança `FileExistsError` se o nome já estiver em uso: nunca sobrescreve.
        """

    @abstractmethod
    async def read(self, reference: str) -> bytes:
        """Lança `FileNotFoundError` se o arquivo não existir mais."""

    @abstractmethod
    async def delete(self, reference: str) -> None:
        """Remove o arquivo; não falha se ele já não existir."""

    @abstractmethod
    async def list_names(self) -> list[str]:
        """Nomes dos arquivos armazenados, em ordem alfabética."""


class ICVOptimizer(ABC):
    """Otimiza o conteúdo do CV para uma vaga (ex.: LLMCVOptimizer).

    Porta separada de `ILLMProvider` (ISP): otimizar um CV é uma regra de
    negócio, não uma capacidade do provedor. Assim Gemini, Ollama e qualquer
    provedor futuro servem ao CV Tailor sem implementar nada específico dele.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Quem otimizou (ex.: o provedor de LLM), gravado em cada CVVersion."""

    @abstractmethod
    async def optimize_cv(
        self,
        job: JobPosting,
        history: CareerHistory,
        *,
        language: OutreachLanguage,
    ) -> TailoredCV:
        """Seleciona e reescreve o histórico em função da vaga.

        Implementações devem garantir que o resultado não tenha
        `TailoredCV.violations_against(history)`, lançando `CVIntegrityError`
        caso não consigam, e `LLMProviderError` se o LLM falhar.
        """


class ICVGenerator(ABC):
    """Gera o documento final do CV (ex.: TypstPdfAdapter)."""

    @property
    @abstractmethod
    def template(self) -> str:
        """Identificador do template usado, gravado em cada CVVersion."""

    @abstractmethod
    async def generate_pdf(self, history: CareerHistory, cv: TailoredCV) -> bytes:
        """Devolve o PDF pronto. Lança `CVRenderError` em caso de falha.

        Onde gravar o arquivo é decisão do chamador (SRP): o gerador só gera.
        """


class ILLMProvider(ABC):
    """Provedor de LLM (ex.: GeminiAdapter, OllamaAdapter)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador do provedor/modelo, ex.: 'gemini:gemini-2.5-flash'."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Gera texto livre. Lança `LLMProviderError` em caso de falha."""

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Gera uma resposta estruturada em JSON (modo JSON nativo do provedor).

        Lança `LLMResponseFormatError` se a resposta não for um objeto JSON
        válido e `LLMProviderError` para demais falhas.
        """

    async def current_name(self) -> str:
        """`name` do provedor que atenderá a próxima chamada (pode mudar em
        tempo de execução, ex.: configurado pelo painel). Padrão: `name`."""
        return self.name

    async def aclose(self) -> None:
        """Libera conexões abertas. Padrão: nada a liberar."""
        return None
