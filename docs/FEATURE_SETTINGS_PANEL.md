Atue como Engenheiro de Software Fullstack Especialista em Python e FastAPI.

Nosso objetivo é implementar a nova funcionalidade de **Painel de Controle / Configurações** no projeto **copilot-job-gil**, migrando todas as configurações e dados de perfil que antes ficavam em arquivos Markdown/JSON locais para tabelas no banco de dados SQLite/PostgreSQL.

---

### 1. Requisitos de UI/UX & Navegação
- **Acesso:** Adicione um botão com ícone de engrenagem (⚙️) no cabeçalho (`Header.tsx` ou equivalente) ao lado dos itens de navegação principais, direcionando para a rota `/settings`.
- **Layout:** O painel deve seguir o padrão visual do **TailAdmin (Tailwind CSS)** e ser organizado em 3 abas principais (Tabs):
  1. **Perfil Profissional (`/settings/profile`):**
     - Formulário para gerenciar os blocos de experiência (+20 anos em TI, Bradesco, Move Tech 40+, Vavá Doces, etc.).
     - Gerenciamento de competências (Python, SQL, AWS, Azure, Kubernetes, Docker, AI/LLMs).
     - Gerenciamento de métricas e conquistas (ex: "Migração de 20TB no S3", "Redução de 76% no tempo de ETL").
  2. **Provedores de IA & Prompts (`/settings/llm`):**
     - Seleção do provedor LLM padrão (`gemini` ou `ollama`).
     - Inclusão/Edição de API Keys.
     - Edição dos Prompts base utilizados pelo `MatchEngine` e pelo `CVTailorService`.
  3. **Conectores & Rate Limits (`/settings/scrapers`):**
     - Configurações do `python-jobspy` (limite de requisições por hora, delay entre requests e plataformas ativas).

---

### 2. Modelo de Dados (`app/domain/models.py`)
Implemente/atualize os modelos com SQLAlchemy:

```python
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from datetime import datetime
from app.repositories.database import Base

class SystemConfig(Base):
    """Parâmetros globais do sistema e integrações."""
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProfileCore(Base):
    """Blocos de experiência e habilidades do perfil."""
    __tablename__ = "profile_core"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False)  # "EXPERIENCE", "SKILL", "METRIC"
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PromptTemplate(Base):
    """Modelos de prompt customizáveis via UI."""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # Ex: "MATCH_ENGINE_PROMPT"
    template_text = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)