"""Erros de domínio.

Adapters traduzem exceções de bibliotecas externas (JobSpy, Gemini, Ollama)
para estes tipos, de modo que os services nunca dependam de erros de SDKs.
"""


class DomainError(Exception):
    """Base de todos os erros do copilot-job-gil."""


class JobSourceError(DomainError):
    """Falha ao consultar uma fonte de vagas."""


class LLMProviderError(DomainError):
    """Falha de comunicação com o provedor de LLM (rede, quota, timeout...)."""


class LLMResponseFormatError(LLMProviderError):
    """O LLM respondeu, mas em um formato que não respeita o contrato esperado."""


class JobNotFoundError(DomainError):
    """A vaga referenciada não está armazenada."""


class ProfileError(DomainError):
    """Perfil do candidato ausente ou inválido."""


class OutreachGenerationError(DomainError):
    """O LLM não produziu uma mensagem que respeite as regras do canal."""
