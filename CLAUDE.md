# Diretrizes do Projeto copilot-job-gil

## 1. Comandos de Execução (Gerenciador `uv`)
- Subir aplicação: `uv run uvicorn main:app --reload`
- Rodar testes: `uv run pytest`
- Adicionar dependência: `uv add <pacote>`

## 2. Padrões de Arquitetura & Código
- Siga estritamente os princípios SOLID.
- Separação em camadas: `app/domain`, `app/services`, `app/adapters`, `app/repositories`, `app/web`.
- Use Pydantic e Type Hints do Python em todas as funções/métodos.

## 3. Economia de Contexto & Delegação
- Para ler arquivos extensos em `docs/`, logs ou relatórios, delegue a leitura a um sub-agente e retorne apenas o resumo executivo das ações necessárias.
