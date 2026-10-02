# copilot-job-gil

Assistente de busca e análise estratégica de vagas.

- **[Guia do Usuário](docs/USER_GUIDE.md):** instalação, configuração, perfil e uso.
- **[Arquitetura](docs/ARCHITECTURE.md):** camadas, decisões de design, testes e como estender.

## Como rodar

```bash
uv sync
cp .env.example .env                                              # valores iniciais (LLM_PROVIDER etc.)
uv run main.py                                                    # http://127.0.0.1:8000
```

- **Interface web:** `http://127.0.0.1:8000` — busca, lista de vagas e análise de match.
- **Painel de configurações:** `http://127.0.0.1:8000/settings` (ícone ⚙ no cabeçalho) — perfil
  profissional, provedor de IA, prompts, plataformas de vagas e limites. O que é salvo ali fica
  no banco e vale na hora, sem reiniciar; o `.env` só fornece os valores iniciais.
- **API JSON:** documentação interativa em `http://127.0.0.1:8000/docs`.
- As migrações do banco são aplicadas automaticamente na subida.
- **Perfil:** cadastre-o em `/settings/profile`. Opcionalmente, copie
  `profile_data/profile.example.json` e `profile_data/profile_base.example.json` (sem o
  `.example`) antes da primeira execução: eles são importados para o banco **uma única vez**, se o
  banco ainda não tiver perfil, e depois não são mais lidos.
- Matches feitos com o perfil antigo aparecem como "perfil mudou" e são recalculados na próxima
  análise.

A aplicação não tem autenticação: ela escuta só em `127.0.0.1` e recusa formulários
enviados por outros sites (verificação de `Origin`/`Referer`). Não a exponha na rede.

## Testes

```bash
uv run pytest            # tudo
uv run pytest -m unit    # ou: regression, e2e
```

## Banco de dados (SQLite + Alembic)

O esquema é versionado com Alembic; a URL vem de `DATABASE_URL` (ver `.env.example`).

```bash
uv run alembic upgrade head                           # aplica as migrações pendentes
uv run alembic revision --autogenerate -m "descrição" # após alterar app/repositories/orm.py
uv run alembic check                                  # confere se modelos e migrações batem
```

O teste `tests/regression/test_migrations.py` falha se um modelo mudar sem a migração correspondente.
