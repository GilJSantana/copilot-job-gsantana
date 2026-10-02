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


class CVIntegrityError(DomainError):
    """O CV otimizado contém algo que não existe no histórico profissional."""

    def __init__(self, violations: list[str]) -> None:
        # args guarda a lista (não a mensagem pronta): exceções recriadas a partir
        # de args, como em cópias e serialização, continuam íntegras
        super().__init__(list(violations))
        self.violations = list(violations)

    def __str__(self) -> str:
        return "CV otimizado diverge do histórico: " + "; ".join(self.violations)


class CVRenderError(DomainError):
    """Falha ao gerar o PDF do CV (template inválido, fonte ausente...)."""


class CVVersionNotFoundError(DomainError):
    """A versão de CV pedida não existe."""


class ProfileBlockNotFoundError(DomainError):
    """O bloco de perfil referenciado não existe."""


class RateLimitExceededError(DomainError):
    """O limite de requisições por hora às plataformas de vagas foi atingido."""


class SourcesDisabledError(DomainError):
    """Nenhuma das plataformas pedidas está ativa nas configurações."""
