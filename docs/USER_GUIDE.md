# Guia do Usuário

O copilot-job-gil busca vagas no LinkedIn, Indeed e outros sites, junta as repetidas, avalia
quanto cada vaga combina com o seu perfil e escreve rascunhos de mensagens para recrutadores.
Tudo roda no seu computador.

Para detalhes de funcionamento interno, veja a [Arquitetura](ARCHITECTURE.md).

## Sumário

1. [Instalação](#1-instalação)
2. [Configuração](#2-configuração)
3. [Seu perfil](#3-seu-perfil)
4. [Usando a interface](#4-usando-a-interface)
5. [Usando a API](#5-usando-a-api)
6. [Seus dados](#6-seus-dados)
7. [Solução de problemas](#7-solução-de-problemas)

---

## 1. Instalação

**Pré-requisitos**

- Python 3.14 ou superior
- [uv](https://docs.astral.sh/uv/)
- Um provedor de LLM, à sua escolha:
  - **Ollama** (local, gratuito): instale em [ollama.com](https://ollama.com) e baixe um modelo
    com `ollama pull llama3.1`;
  - **Gemini** (na nuvem): crie uma chave de API no [Google AI Studio](https://aistudio.google.com).

**Passos**

```bash
uv sync                                                           # instala as dependências
cp .env.example .env                                              # configuração
cp profile_data/profile.example.json profile_data/profile.json   # seu perfil
uv run main.py                                                    # inicia a aplicação
```

Abra **http://127.0.0.1:8000** no navegador. Na primeira execução, o banco de dados
(`copilot_job.db`) é criado automaticamente.

## 2. Configuração

Edite o arquivo `.env`. Todas as variáveis são opcionais: sem elas, valem os valores padrão.

### Provedor de LLM

| Variável | Padrão | Descrição |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` ou `gemini` |
| `LLM_TIMEOUT_SECONDS` | `120` | Tempo máximo de espera por resposta do LLM |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endereço do Ollama |
| `OLLAMA_MODEL` | `llama3.1` | Modelo do Ollama (precisa estar baixado) |
| `GEMINI_API_KEY` | — | **Obrigatória** se `LLM_PROVIDER=gemini` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo do Gemini |

**Qual escolher?** O Ollama é gratuito e seus dados não saem do computador, mas é mais lento
(cerca de 1 minuto por análise com o `llama3.1`) e escreve mensagens mais genéricas. O Gemini é
mais rápido e escreve melhor, mas envia o seu perfil e as vagas para o Google.

### Busca de vagas

| Variável | Padrão | Descrição |
|---|---|---|
| `JOBSPY_MIN_DELAY_SECONDS` | `2` | Pausa mínima entre sites |
| `JOBSPY_MAX_DELAY_SECONDS` | `6` | Pausa máxima entre sites |
| `JOBSPY_LINKEDIN_FETCH_DESCRIPTION` | `true` | Busca a descrição completa no LinkedIn: mais lento, mas sem ela a análise de match fica pobre |

A pausa entre sites é sorteada dentro da faixa, para reduzir o risco de bloqueio. Se começar a
receber bloqueios, aumente os valores.

### Outros

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./copilot_job.db` | Arquivo do banco |
| `PROFILE_PATH` | `profile_data/profile.json` | Arquivo do perfil |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` ou `ERROR` |

Se a configuração tiver um erro, por exemplo Gemini sem chave, a aplicação não inicia e mostra o
motivo.

## 3. Seu perfil

O arquivo `profile_data/profile.json` é a **única fonte de informações sobre você** usada nas
análises e nas mensagens. O LLM é instruído a nunca inventar nada além do que estiver ali.

```json
{
  "full_name": "Seu Nome",
  "headline": "Backend Developer Python",
  "summary": "Resumo profissional em 2-3 frases.",
  "years_of_experience": 5,
  "skills": ["Python", "FastAPI", "SQLAlchemy", "Docker", "PostgreSQL"],
  "target_roles": ["Backend Engineer", "Python Developer"],
  "preferred_locations": ["São Paulo", "Remoto"],
  "preferred_work_modes": ["remote", "hybrid"],
  "languages": ["Português", "Inglês"]
}
```

| Campo | Obrigatório | Observações |
|---|---|---|
| `full_name` | sim | Usado na assinatura das mensagens |
| `headline` | sim | Seu título profissional |
| `skills` | sim (ao menos 1) | **O campo mais importante:** 40% do score vem de quantas delas a vaga cita |
| `summary` | não | Dá contexto ao LLM; escreva conquistas concretas |
| `years_of_experience` | não | Número ≥ 0 |
| `target_roles` | não | Cargos que você procura |
| `preferred_locations` | não | |
| `preferred_work_modes` | não | `remote`, `hybrid` e/ou `onsite` |
| `languages` | não | |

**Dicas para as skills**

- Liste as tecnologias com os nomes usados nas vagas: "PostgreSQL", e não "Postgres (avançado)".
- A comparação ignora maiúsculas e acentos, mas exige a palavra inteira: "Java" não conta como
  "JavaScript".
- Uma lista enorme dilui o score: com 30 skills, uma vaga que cita 5 delas fica com 17% nessa
  parte. Prefira as 8 a 15 mais relevantes para as vagas que você busca.

**Você pode editar o perfil com a aplicação rodando.** A mudança vale na hora, sem reiniciar.
As análises feitas com a versão anterior passam a aparecer como **"perfil mudou"** e são
refeitas quando você clicar em "Reanalisar".

## 4. Usando a interface

### Buscar vagas

Na página inicial, preencha:

- **Cargo ou palavra-chave:** ex.: `python developer`, `engenheiro de dados`;
- **Local:** ex.: `São Paulo`, `Brazil`;
- **Sites:** LinkedIn e Indeed vêm marcados;
- **Vagas por site:** de 1 a 100 (padrão 20);
- **Publicadas nas últimas (horas):** padrão 72; deixe vazio para qualquer data;
- **Somente remotas.**

A busca leva de alguns segundos a alguns minutos, conforme a quantidade de vagas e sites. O botão
mostra "Buscando…" enquanto isso: não recarregue a página.

Se um site falhar (por exemplo, o LinkedIn bloquear temporariamente), as vagas dos outros sites
aparecem normalmente. Só aparece erro se **todos** falharem.

### A lista de vagas

Cada vaga mostra empresa, local, modelo de trabalho, data, salário (quando informado) e links
para **todos os sites** onde ela foi encontrada. Etiquetas:

| Etiqueta | Significado |
|---|---|
| **Nova** | Aparece logo após uma busca: a vaga nunca tinha sido vista antes |
| **85% · Match forte** | Resultado da análise (a cor indica o veredito) |
| **perfil mudou** | A análise foi feita com uma versão anterior do seu perfil |
| **sem LLM** | O LLM não respondeu na hora da análise; o score considera só as skills |

**Vagas repetidas são juntadas automaticamente.** A mesma vaga publicada no LinkedIn e no
Indeed, ou a mesma vaga remota publicada em várias cidades, aparece uma vez só, com os links de
todos os anúncios. O resumo da busca informa quantas duplicatas foram removidas.

A lista inicial mostra as vagas mais recentes primeiro, 25 por página.

### Analisar o match

Na página da vaga, clique em **Analisar match**. O resultado combina:

- **Skills (40%):** porcentagem das suas skills citadas na vaga;
- **LLM (60%):** avaliação do LLM sobre a aderência geral.

| Score | Veredito |
|---|---|
| 80 ou mais | Match forte |
| 65 a 79 | Bom match |
| 45 a 64 | Match fraco |
| abaixo de 45 | Pouca aderência |

A análise também lista as skills encontradas, os pontos fortes e as lacunas.

A análise é **salva**: abrir a vaga de novo não chama o LLM outra vez. Ela só é refeita quando
você clica em **Reanalisar**, e é refeita automaticamente se o seu perfil mudou ou se a análise
anterior foi feita sem o LLM.

### Mensagem para recrutador

Na página da vaga, na seção **Mensagem para recrutador**, escolha:

| Canal | Tamanho máximo |
|---|---|
| Convite de conexão (LinkedIn) | 300 caracteres (limite do LinkedIn) |
| Mensagem (LinkedIn) | 1000 caracteres |
| E-mail | 1500 caracteres, com assunto |

Escolha também o **idioma** (português ou inglês) e, se souber, o **nome do destinatário**.
Clique em **Gerar rascunho** e use **Copiar** para levar o texto ao LinkedIn ou ao e-mail.

- Se a vaga já tiver uma análise de match atualizada, a mensagem destaca os seus pontos fortes
  para aquela vaga. As lacunas nunca são mencionadas.
- Cada geração cria um rascunho novo; os anteriores continuam na página.
- **Sempre revise antes de enviar.** O LLM é instruído a usar só fatos do seu perfil, mas pode
  errar o tom ou escrever de forma genérica.

## 5. Usando a API

A documentação interativa fica em **http://127.0.0.1:8000/docs**. Exemplos:

```bash
# Buscar vagas
curl -X POST http://127.0.0.1:8000/api/searches \
  -H "Content-Type: application/json" \
  -d '{"search_term": "python developer", "location": "São Paulo", "sites": ["linkedin", "indeed"], "results_wanted": 10}'

# Listar vagas salvas (paginação com limit e offset)
curl "http://127.0.0.1:8000/api/jobs?limit=20&offset=0"

# Detalhe de uma vaga (a chave vem da listagem, campo "key")
curl http://127.0.0.1:8000/api/jobs/<key>

# Analisar o match (force=true refaz mesmo se já houver análise válida)
curl -X POST "http://127.0.0.1:8000/api/jobs/<key>/match?force=false"

# Gerar rascunho de mensagem: channel = linkedin_connection | linkedin_message | email
curl -X POST http://127.0.0.1:8000/api/jobs/<key>/outreach \
  -H "Content-Type: application/json" \
  -d '{"channel": "email", "language": "en", "recipient_name": "Ana"}'

# Rascunhos já gerados para a vaga
curl http://127.0.0.1:8000/api/jobs/<key>/outreach

# Perfil carregado e situação da aplicação
curl http://127.0.0.1:8000/api/profile
curl http://127.0.0.1:8000/api/health
```

Erros vêm como `{"detail": "mensagem"}`:

| Status | Quando |
|---|---|
| 403 | Requisição enviada por outro site pelo navegador |
| 404 | Vaga não encontrada |
| 422 | Dados inválidos na requisição |
| 502 | Todos os sites de vagas falharam, ou o LLM respondeu em formato inválido |
| 503 | LLM fora do ar, ou perfil ausente ou inválido |

## 6. Seus dados

Tudo fica no seu computador:

| O quê | Onde |
|---|---|
| Vagas, análises e rascunhos | `copilot_job.db` (e os arquivos `-wal` e `-shm` ao lado dele) |
| Perfil | `profile_data/profile.json` |
| Configuração e chave do Gemini | `.env` |

Esses arquivos estão no `.gitignore` e não vão para o repositório.

- **Backup:** pare a aplicação e copie `copilot_job.db`.
- **Começar do zero:** pare a aplicação e apague `copilot_job.db`, `copilot_job.db-wal` e
  `copilot_job.db-shm`. O banco é recriado vazio na próxima execução.
- **Privacidade:** com o **Ollama**, perfil e vagas não saem do computador. Com o **Gemini**,
  perfil e descrições de vagas são enviados ao Google a cada análise e rascunho.
- **Segurança:** a aplicação não tem login e aceita conexões só do próprio computador
  (`127.0.0.1`). Não altere isso para expô-la na rede.

## 7. Solução de problemas

**"Perfil não encontrado em profile_data/profile.json"**
Copie o exemplo: `cp profile_data/profile.example.json profile_data/profile.json`.

**"Perfil inválido em … — skills: …"**
A mensagem indica o campo com problema. Causas comuns: `skills` vazio, `years_of_experience`
negativo, valor desconhecido em `preferred_work_modes`, ou um campo com o nome digitado errado
(por exemplo, `skils`). Campos desconhecidos são recusados de propósito, para pegar erros de
digitação.

**As análises aparecem como "sem LLM"**
O LLM não respondeu na hora da análise.
- **Ollama:** confira se está rodando (`curl http://localhost:11434/api/tags`) e se o modelo de
  `OLLAMA_MODEL` aparece na lista. Se não aparecer, rode `ollama pull <modelo>`.
- **Gemini:** confira a chave e a quota no Google AI Studio.

Depois, clique em **Reanalisar**.

**"Falha de rede ao chamar o Ollama" ou "Ollama HTTP 404: model '…' not found"**
Ao gerar mensagens, o LLM é obrigatório: veja o item anterior.

**"GEMINI_API_KEY é obrigatória quando LLM_PROVIDER=gemini" ao iniciar**
Defina `GEMINI_API_KEY` no `.env`, ou volte para `LLM_PROVIDER=ollama`.

**"Nenhuma fonte respondeu"**
Todos os sites falharam, geralmente por bloqueio temporário. Espere alguns minutos, aumente
`JOBSPY_MIN_DELAY_SECONDS` e `JOBSPY_MAX_DELAY_SECONDS`, ou busque em menos sites.

**A busca retorna poucas vagas**
Tente termos mais amplos, aumente "Publicadas nas últimas (horas)" ou deixe esse campo vazio.
Alguns sites devolvem menos vagas do que o pedido.

**Análises ou mensagens demoram muito**
Com o Ollama rodando no processador, espere de 1 a 1,5 minuto por operação. Um modelo menor, uma
GPU ou o Gemini deixam tudo mais rápido. Se o LLM passar de `LLM_TIMEOUT_SECONDS`, a análise de
match fica "sem LLM" e a geração de mensagem falha: nesse caso, aumente o valor.

**"O LLM gerou N caracteres mesmo após pedido de reescrita"**
O modelo não conseguiu respeitar o limite do canal. Tente de novo, ou escolha um canal com
limite maior.

**A página aparece sem formatação**
O estilo é carregado da internet (Tailwind via CDN). Confira sua conexão.

**"Requisição de outra origem bloqueada" (403)**
Proteção contra sites maliciosos. Use a aplicação pelo endereço `http://127.0.0.1:8000` e não
envie formulários a partir de outras páginas.
