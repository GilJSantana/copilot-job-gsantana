"""Remoção de vagas duplicadas entre fontes, preservando a informação mais rica."""

from app.domain.models import JobPosting


class JobDeduplicator:
    """Agrupa vagas pelo `dedup_key` e funde cada grupo em uma só.

    A primeira ocorrência define a identidade exibida (URL, fonte, título); as
    demais só completam lacunas (ver `JobPosting.merged_with`). Assim, a ordem
    dos sites na busca expressa a preferência do usuário.
    """

    def deduplicate(self, jobs: list[JobPosting]) -> list[JobPosting]:
        merged: dict[str, JobPosting] = {}
        for job in jobs:
            key = job.dedup_key
            merged[key] = merged[key].merged_with(job) if key in merged else job
        return list(merged.values())
