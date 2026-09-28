"""Portas (interfaces) do domínio.

Services dependem apenas destas abstrações (DIP). Cada interface é pequena e
focada em um único papel (ISP); novos provedores entram como novos adapters
sem alterar os services (OCP).
"""

from abc import ABC, abstractmethod
from typing import Any

from app.domain.models import (
    CandidateProfile,
    JobPosting,
    JobSearchCriteria,
    MatchResult,
    OutreachMessage,
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
    """Origem do perfil do candidato (ex.: JsonProfileRepository)."""

    @abstractmethod
    async def get(self) -> CandidateProfile:
        """Lança `ProfileError` se o perfil não existir ou for inválido."""


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

    async def aclose(self) -> None:
        """Libera conexões abertas. Padrão: nada a liberar."""
        return None
