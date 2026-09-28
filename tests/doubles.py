"""Test doubles compartilhados entre as suítes unit/regression/e2e."""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import (
    IJobRepository,
    IJobStore,
    ILLMProvider,
    IMatchResultStore,
    IOutreachStore,
)
from app.domain.models import JobPosting, JobSearchCriteria, MatchResult, OutreachMessage


class MockLLMAdapter(ILLMProvider):
    """LLM falso: devolve uma resposta pré-configurada (ou lança um erro) e
    registra todas as chamadas para inspeção nos testes."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._response = response or {}
        self._error = error
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        return json.dumps(await self.generate_json(prompt, system_prompt=system_prompt))

    async def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if self._error is not None:
            raise self._error
        return copy.deepcopy(self._response)


class FakeJobRepository(IJobRepository):
    """Fonte de vagas falsa: devolve vagas fixas (ou lança um erro) e registra os critérios."""

    def __init__(
        self,
        jobs: list[JobPosting] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._jobs = jobs or []
        self._error = error
        self.calls: list[JobSearchCriteria] = []

    async def search(self, criteria: JobSearchCriteria) -> list[JobPosting]:
        self.calls.append(criteria)
        if self._error is not None:
            raise self._error
        return list(self._jobs)


class InMemoryJobStore(IJobStore):
    """Armazenamento em memória com a mesma semântica do SqlAlchemyJobStore
    (garantida pelos testes de contrato em tests/regression)."""

    def __init__(self) -> None:
        self.jobs: dict[str, JobPosting] = {}
        self._batch_of: dict[str, int] = {}
        self._batches = 0

    async def save_many(self, jobs: list[JobPosting]) -> set[str]:
        self._batches += 1
        new_keys = set()
        for job in jobs:
            key = job.dedup_key
            if key in self.jobs:
                self.jobs[key] = self.jobs[key].merged_with(job)
            else:
                self.jobs[key] = job
                self._batch_of[key] = self._batches
                new_keys.add(key)
        return new_keys

    async def get(self, dedup_key: str) -> JobPosting | None:
        return self.jobs.get(dedup_key)

    async def list_recent(self, *, limit: int = 50, offset: int = 0) -> list[JobPosting]:
        if limit <= 0 or offset < 0:
            raise ValueError("exige limit > 0 e offset >= 0")
        # lote mais recente primeiro; dentro do lote, a ordem da busca
        ordered = sorted(self.jobs, key=lambda key: -self._batch_of[key])
        return [self.jobs[key] for key in ordered[offset : offset + limit]]


class InMemoryMatchResultStore(IMatchResultStore):
    """Matches em memória com a mesma semântica do SqlAlchemyMatchResultStore
    (garantida pelos testes de contrato em tests/regression)."""

    def __init__(self, job_store: InMemoryJobStore) -> None:
        self._job_store = job_store
        self.results: dict[str, MatchResult] = {}

    async def save(self, result: MatchResult) -> None:
        if result.job_key not in self._job_store.jobs:
            raise JobNotFoundError(f"vaga {result.job_key} não está armazenada")
        self.results[result.job_key] = result

    async def get(self, job_key: str) -> MatchResult | None:
        if job_key not in self._job_store.jobs:  # espelha o ON DELETE CASCADE
            return None
        return self.results.get(job_key)

    async def get_many(self, job_keys: list[str]) -> dict[str, MatchResult]:
        return {key: result for key in job_keys if (result := await self.get(key)) is not None}


class InMemoryOutreachStore(IOutreachStore):
    """Rascunhos em memória com a mesma semântica do SqlAlchemyOutreachStore
    (garantida pelos testes de contrato em tests/regression)."""

    def __init__(self, job_store: InMemoryJobStore) -> None:
        self._job_store = job_store
        self.messages: list[OutreachMessage] = []
        self._now = datetime(2026, 9, 1, tzinfo=UTC)

    async def save(self, message: OutreachMessage) -> OutreachMessage:
        if message.job_key not in self._job_store.jobs:
            raise JobNotFoundError(f"vaga {message.job_key} não está armazenada")
        self._now += timedelta(seconds=1)
        saved = replace(message, created_at=self._now)
        self.messages.append(saved)
        return saved

    async def list_for_job(self, job_key: str) -> list[OutreachMessage]:
        if job_key not in self._job_store.jobs:  # espelha o ON DELETE CASCADE
            return []
        return [m for m in reversed(self.messages) if m.job_key == job_key]


class ScriptedLLMAdapter(MockLLMAdapter):
    """Devolve uma resposta diferente a cada chamada, na ordem dada."""

    def __init__(self, *responses: dict[str, Any]) -> None:
        super().__init__()
        self._responses = list(responses)

    async def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return copy.deepcopy(self._responses.pop(0))
