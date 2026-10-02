# Guia do Usuário

O copilot-job-gil busca vagas no LinkedIn, Indeed e outros sites, junta as repetidas, avalia
quanto cada vaga combina com o seu perfil e escreve rascunhos de mensagens para recrutadores.
Tudo roda no seu computador.

Para detalhes de funcionamento interno, veja a [Arquitetura](ARCHITECTURE.md).

## Sumário

1. [Instalação](#1-instalação)
2. [Configuração](#2-configuração)
3. [Painel de configurações](#3-painel-de-configurações)
4. [Seu perfil](#4-seu-perfil)
5. [Seu histórico profissional (CV Tailor)](#5-seu-histórico-profissional-cv-tailor)
6. [Usando a interface](#6-usando-a-interface)
7. [Usando a API](#7-usando-a-api)
8. [Seus dados](#8-seus-dados)
9. [Solução de problemas](#9-solução-de-problemas)

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
cp .env.example .env                                              # configuração inicial
uv run main.py                                                    # inicia a aplicação
```

Abra **http://127.0.0.1:8000** no navegador. Na primeira execução, o banco de dados
(`copilot_job.db`) é criado automaticamente. Depois, cadastre o seu perfil em
**http://127.0.0.1:8000/settings/profile** (veja a [seção 3](#3-painel-de-configurações)).

**Importação opcional de arquivos JSON.** Se você já tem o perfil em arquivos, copie-os antes da
primeira execução:

```bash
cp profile_data/profile.example.json profile_data/profile.json             # perfil (match)
cp profile_data/profile_base.example.json profile_data/profile_base.json   # histórico (CV Tailor)
```

Na subida, se o banco **ainda não tiver perfil**, o conteúdo desses arquivos é copiado para ele.
Isso acontece **uma única vez**: depois disso os arquivos não são mais lidos, e editá-los não tem
efeito. Arquivos ausentes ou inválidos são ignorados (com um aviso no log) e a aplicação sobe
normalmente. Na importação:

- nome, headline, resumo, contato, formação, certificações e idioma vêm do `profile_base.json`,
  se existir, e senão do `profile.json`;
- anos de experiência, cargos-alvo, locais e modelos de trabalho preferidos vêm do
  `profile.json`;
- as experiências vêm do `profile_base.json`;
- as skills dos dois arquivos são unidas, sem repetição (ignorando maiúsculas e acentos).

## 2. Configuração

Edite o arquivo `.env`. Todas as variáveis são opcionais: sem elas, valem os valores padrão.

**O `.env` fornece os valores iniciais.** As configurações de LLM e de busca de vagas também
podem ser alteradas no [painel](#3-painel-de-configurações): o que for salvo lá fica no banco,
passa a valer no lugar do `.env` e entra em vigor sem reiniciar. Enquanto o painel não salvar um
valor, vale o do `.env`. As demais variáveis (tempos limite, banco, CV Tailor, logs) só existem
no `.env`.

### Provedor de LLM

| Variável | Padrão | Descrição |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` ou `gemini` (alterável no painel) |
| `LLM_TIMEOUT_SECONDS` | `120` | Tempo máximo de espera por resposta do LLM |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endereço do Ollama (alterável no painel) |
| `OLLAMA_MODEL` | `llama3.1` | Modelo do Ollama, que precisa estar baixado (alterável no painel) |
| `GEMINI_API_KEY` | — | **Obrigatória** se `LLM_PROVIDER=gemini` (alterável no painel) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo do Gemini (alterável no painel) |

**Qual escolher?** O Ollama é gratuito e seus dados não saem do computador, mas é mais lento
(cerca de 1 minuto por análise com o `llama3.1`) e escreve mensagens mais genéricas. O Gemini é
mais rápido e escreve melhor, mas envia o seu perfil e as vagas para o Google.

### Busca de vagas

Todas alteráveis no painel, em **Conectores & Rate Limits**.

| Variável | Padrão | Descrição |
|---|---|---|
| `JOBSPY_MIN_DELAY_SECONDS` | `2` | Pausa mínima entre sites |
| `JOBSPY_MAX_DELAY_SECONDS` | `6` | Pausa máxima entre sites |
| `JOBSPY_MAX_REQUESTS_PER_HOUR` | `60` | Limite de requisições aos sites por hora; cada site consultado em uma busca conta uma. `0` = sem limite |
| `JOBSPY_LINKEDIN_FETCH_DESCRIPTION` | `true` | Busca a descrição completa no LinkedIn: mais lento, mas sem ela a análise de match fica pobre |

A pausa entre sites é sorteada dentro da faixa, para reduzir o risco de bloqueio. Se começar a
receber bloqueios, aumente os valores. Inicialmente, as cinco plataformas (LinkedIn, Indeed,
Glassdoor, Google e ZipRecruiter) ficam ativas; desative as que não usa no painel.

### Outros

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./copilot_job.db` | Arquivo do banco |
| `PROFILE_PATH` | `profile_data/profile.json` | Perfil a importar na primeira execução (veja a [seção 1](#1-instalação)) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` ou `ERROR` |

### CV Tailor

| Variável | Padrão | Descrição |
|---|---|---|
| `CAREER_HISTORY_PATH` | `profile_data/profile_base.json` | Histórico a importar na primeira execução (veja a [seção 1](#1-instalação)) |
| `CV_OUTPUT_DIR` | `output_cvs` | Pasta onde os PDFs são gravados |
| `CV_TEMPLATE_PATH` | `templates/cv/ats_base.typ` | Template do currículo |
| `CV_PDF_STANDARD` | `ua-1` | `ua-1` (acessibilidade validada), `a-2a` (arquivamento) ou `none` |
| `CV_LLM_TIMEOUT_SECONDS` | `600` | Tempo máximo para o LLM otimizar um CV. É maior que `LLM_TIMEOUT_SECONDS` porque a resposta é o currículo inteiro |

Se a configuração do `.env` tiver um erro, por exemplo Gemini sem chave, a aplicação não inicia e
mostra o motivo. O painel faz as mesmas verificações antes de salvar.

## 3. Painel de configurações

Abra **http://127.0.0.1:8000/settings** ou clique no ícone **⚙** no cabeçalho. O painel tem três
abas. Cada formulário é salvo separadamente e mostra uma confirmação; se houver um erro, a página
indica o campo e mantém o que você digitou.

### Perfil Profissional (`/settings/profile`)

O seu perfil e o seu histórico profissional são **uma única fonte**, guardada no banco: a mesma
informação alimenta a análise de match, as mensagens para recrutadores e os currículos. A aba tem
quatro cartões:

| Cartão | Conteúdo |
|---|---|
| **Dados gerais** | Nome, headline, resumo, anos de experiência, contato, cargos-alvo, locais e modelos de trabalho preferidos, idiomas, formação, certificações e idioma do histórico |
| **Experiências** | Cargo, empresa, local, período e conquistas de cada emprego |
| **Competências** | As suas skills: adicionar, ativar/desativar e remover |
| **Métricas e conquistas** | Resultados de destaque, com detalhes opcionais |

Experiências, competências e conquistas **inativas** continuam cadastradas, mas ficam fora do
match e dos CVs. Os detalhes de cada cartão estão nas seções [4](#4-seu-perfil) e
[5](#5-seu-histórico-profissional-cv-tailor).

### Provedores de IA & Prompts (`/settings/llm`)

- **Provedor de LLM padrão:** Google Gemini ou Ollama, com o modelo de cada um, a URL do servidor
  Ollama e a API key do Gemini.
- **API key do Gemini:** fica salva no banco local, em texto puro, e é exibida só mascarada
  (`••••` e os 4 últimos caracteres). Deixe o campo em branco para manter a chave salva, ou marque
  a opção de remoção para apagá-la. O Gemini exige uma chave.
- **Prompts base:** o system prompt da análise de match (`MATCH_ENGINE_PROMPT`) e o da otimização
  do CV (`CV_TAILOR_PROMPT`) podem ser editados. **Salvar prompt** grava a sua versão;
  **Restaurar padrão** volta ao prompt original. Salvar um texto idêntico ao padrão também remove
  a personalização.

> **Mantenha o formato de resposta JSON** descrito no final de cada prompt. Se ele for alterado,
> o LLM passa a responder fora do contrato: a análise de match fica "sem LLM" e a geração de CV
> falha.

A troca de provedor, modelo ou chave vale a partir da próxima chamada ao LLM, sem reiniciar.

### Conectores & Rate Limits (`/settings/scrapers`)

| Campo | Descrição |
|---|---|
| **Plataformas ativas** | Só elas aparecem na página de busca. Ao menos uma |
| **Requisições por hora** | Cada plataforma consultada em uma busca conta uma. `0` = sem limite |
| **Delay mínimo / máximo** | Pausa entre requisições, sorteada entre os dois valores (mínimo ≤ máximo) |
| **Buscar a descrição completa no LinkedIn** | Mais lento, mas melhora a análise de match |

As mudanças valem a partir da próxima busca. A contagem do limite por hora fica na memória: ela
recomeça quando a aplicação é reiniciada.

## 4. Seu perfil

Os **Dados gerais** e as **Competências** da aba Perfil Profissional são a **base de informações
sobre você** usada nas análises e nas mensagens. O LLM é instruído a nunca inventar nada além do
que estiver ali. A análise de match também recebe um resumo de uma linha de cada experiência
ativa e as suas métricas e conquistas.

| Campo | Obrigatório | Observações |
|---|---|---|
| Nome completo | sim | Usado na assinatura das mensagens |
| Headline | sim | Seu título profissional |
| Competências | sim (ao menos 1 ativa) | **O campo mais importante:** 40% do score vem de quantas delas a vaga cita |
| Resumo profissional | não | Dá contexto ao LLM e é a base do resumo dos CVs; escreva conquistas concretas |
| Anos de experiência | não | Número ≥ 0 |
| Cargos-alvo | não | Separados por vírgula |
| Locais preferidos | não | Separados por vírgula |
| Modelos de trabalho preferidos | não | Remoto, híbrido e/ou presencial |
| Idiomas | não | Separados por vírgula |

**Dicas para as competências**

- Liste as tecnologias com os nomes usados nas vagas: "PostgreSQL", e não "Postgres (avançado)".
- A comparação ignora maiúsculas e acentos, mas exige a palavra inteira: "Java" não conta como
  "JavaScript".
- Uma lista enorme dilui o score: com 30 skills, uma vaga que cita 5 delas fica com 17% nessa
  parte. Prefira as 8 a 15 mais relevantes para as vagas que você busca. Em vez de remover as
  demais, você pode **desativá-las**.

**As mudanças valem na hora**, sem reiniciar. As análises feitas com a versão anterior passam a
aparecer como **"perfil mudou"** e são refeitas quando você clicar em "Reanalisar".

## 5. Seu histórico profissional (CV Tailor)

O CV Tailor gera, para cada vaga, um currículo em PDF otimizado para ATS (os sistemas que fazem a
triagem automática de currículos). Ele parte do seu **histórico completo**, cadastrado na aba
**Perfil Profissional** do painel, com mais conteúdo do que caberia em um currículo. Para cada
vaga, o LLM escolhe e reescreve o que é mais relevante.

Esta seção descreve o que cadastrar e as regras. Para gerar os currículos, veja
[Gerar o currículo](#gerar-o-currículo) na seção 6.

O histórico usa os **Dados gerais** (nome, headline, contato, resumo, competências, formação,
certificações, idiomas e idioma do histórico), mais:

| Cartão / campo | Observações |
|---|---|
| **Experiências** | Ao menos uma ativa. Todas as ativas entram no CV, da mais recente para a mais antiga |
| Identificador | Opcional ao criar: se ficar em branco, é gerado a partir da empresa ("Move Tech 40+" → `move-tech-40`). Só letras minúsculas, números, `-` e `_`. **Não muda depois de criado**, porque as versões de CV o referenciam |
| Início, Término | Formato `AAAA-MM`; término em branco significa emprego atual |
| Conquistas e responsabilidades | Uma por linha. **Onde está o valor.** Veja as regras abaixo |
| Tecnologias | Separadas por vírgula. Tecnologias usadas naquela experiência: também contam como skills suas |
| **Métricas e conquistas** | Resultados de destaque, com detalhes opcionais. Os números citados aqui podem aparecer no resumo do CV |
| Formação | Uma por linha: `Grau \| Instituição \| AAAA-MM \| AAAA-MM` |
| Certificações | Uma por linha: `Nome \| Emissor \| Ano` |
| Idioma do histórico | Português ou inglês: idioma em que o histórico está escrito |

### O que o CV Tailor pode e não pode fazer

O histórico é a **única fonte de fatos**. Cada CV gerado é conferido contra ele, e o que não
tiver lastro é corrigido ou removido automaticamente:

- **Nada de experiências, empresas ou skills novas.** Só entram competências cadastradas ou
  tecnologias de alguma experiência.
- **Nada de números novos.** Todo número de uma conquista (%, ms, R$, tamanho de equipe) precisa
  existir no texto original daquela experiência. "800 ms para 120 ms" não pode virar "para 50 ms".
  Números do título e do resumo do CV precisam existir em algum ponto do histórico, inclusive nas
  métricas e conquistas.
- **Nada de responsabilidades copiadas da vaga.** Cada conquista precisa ser uma reescrita de
  algo que está na sua experiência.

**Por isso, cadastre todas as suas conquistas, com os números reais.** Por exemplo: "Reduzi a
latência p95 da API de 800 ms para 120 ms migrando para FastAPI." Quanto mais rico o histórico,
melhor o CV: o LLM não pode inventar, só escolher e reescrever.

> A conferência de reescrita é feita por palavras. Se você gerar o CV em um idioma diferente do
> histórico (ex.: histórico em português, CV em inglês), só números e skills são conferidos.
> Revise com atenção nesse caso.

Assim como o perfil, o histórico pode ser editado com a aplicação rodando: a mudança vale na
hora.

## 6. Usando a interface

### Buscar vagas

Na página inicial, preencha:

- **Cargo ou palavra-chave:** ex.: `python developer`, `engenheiro de dados`;
- **Local:** ex.: `São Paulo`, `Brazil`;
- **Sites:** só aparecem as plataformas ativas no painel (aba **Conectores & Rate Limits**);
  LinkedIn e Indeed vêm marcados, se estiverem ativos;
- **Vagas por site:** de 1 a 100 (padrão 20);
- **Publicadas nas últimas (horas):** padrão 72; deixe vazio para qualquer data;
- **Somente remotas.**

A busca leva de alguns segundos a alguns minutos, conforme a quantidade de vagas e sites. O botão
mostra "Buscando…" enquanto isso: não recarregue a página.

Se um site falhar (por exemplo, o LinkedIn bloquear temporariamente), as vagas dos outros sites
aparecem normalmente. Só aparece erro se **todos** falharem.

Cada site consultado conta uma requisição no **limite por hora** definido no painel. Se a busca
ultrapassar o limite, ela não é feita e a página informa quantos minutos esperar
("Limite de 60 requisições por hora atingido. Tente novamente em 12 min…"). Escolha menos sites,
espere ou aumente o limite em `/settings/scrapers`.

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

### Gerar o currículo

Na página da vaga, na seção **Currículo para esta vaga**, escolha o idioma e clique em **Gerar
CV**. Com o Ollama no processador, leva de 1 a 3 minutos; o botão mostra "Gerando CV…" enquanto
isso.

Cada versão gerada mostra:

- o título e o resumo escritos para a vaga;
- **Termos da vaga cobertos:** palavras-chave da vaga que o currículo contém;
- em "Experiências e skills desta versão", exatamente o que entrou no PDF;
- **Ver PDF**, que abre no navegador, e **Baixar**, que salva com um nome como
  `Seu-Nome_CV_Empresa.pdf`;
- a etiqueta **histórico mudou**, se você editou o histórico no painel depois de gerar a versão.

Cada clique em **Gerar nova versão** cria uma versão nova; as anteriores continuam disponíveis.
Os PDFs ficam em `output_cvs/`.

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

## 7. Usando a API

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

# Gerar um currículo otimizado para a vaga (language = pt | en)
curl -X POST http://127.0.0.1:8000/api/jobs/<key>/cvs \
  -H "Content-Type: application/json" -d '{"language": "pt"}'

# Versões de currículo da vaga, e uma versão específica (o id vem da resposta acima)
curl http://127.0.0.1:8000/api/jobs/<key>/cvs
curl http://127.0.0.1:8000/api/cvs/<id>

# O PDF: exibido no navegador, ou baixado com o nome amigável
curl -o cv.pdf "http://127.0.0.1:8000/api/cvs/<id>/pdf?download=true"

# Perfil cadastrado e situação da aplicação (provedor de LLM configurado no painel)
curl http://127.0.0.1:8000/api/profile
curl http://127.0.0.1:8000/api/health
```

Erros vêm como `{"detail": "mensagem"}`:

| Status | Quando |
|---|---|
| 403 | Requisição enviada por outro site pelo navegador |
| 404 | Vaga ou versão de currículo não encontrada, ou PDF removido do disco |
| 422 | Dados inválidos na requisição, ou nenhuma das plataformas pedidas está ativa no painel |
| 429 | Limite de requisições por hora aos sites de vagas atingido (a mensagem diz quanto esperar) |
| 500 | Falha ao gerar o PDF do currículo (template) |
| 502 | Todos os sites de vagas falharam, o LLM respondeu em formato inválido, ou não produziu um currículo fiel ao histórico |
| 503 | LLM fora do ar, ou perfil ou histórico não cadastrado ou inválido |

## 8. Seus dados

Tudo fica no seu computador:

| O quê | Onde |
|---|---|
| Vagas, análises e rascunhos | `copilot_job.db` (e os arquivos `-wal` e `-shm` ao lado dele) |
| Perfil, histórico profissional, configurações do painel e prompts personalizados | `copilot_job.db` |
| Chave do Gemini | `.env` e, se salva pelo painel, `copilot_job.db` (em texto puro) |
| CVs gerados (PDF) | `output_cvs/` |
| Configuração inicial | `.env` |
| Perfil e histórico a importar na primeira execução (opcionais) | `profile_data/profile.json` e `profile_data/profile_base.json` |

Esses arquivos estão no `.gitignore` e não vão para o repositório.

- **Backup:** pare a aplicação e copie `copilot_job.db` e a pasta `output_cvs/`.
- **Começar do zero:** pare a aplicação e apague `copilot_job.db`, `copilot_job.db-wal` e
  `copilot_job.db-shm`. O banco é recriado vazio na próxima execução. **Atenção:** isso apaga
  também o perfil, o histórico e as configurações do painel. Se `profile.json` ou
  `profile_base.json` existirem, eles são importados de novo.
- **Privacidade:** com o **Ollama**, perfil e vagas não saem do computador. Com o **Gemini**,
  perfil, histórico e descrições de vagas são enviados ao Google a cada análise, rascunho e CV.
- **PDFs esquecidos:** se versões de CV sumirem do banco (por exemplo, ao apagar vagas), os PDFs
  continuam em `output_cvs/`. Para encontrá-los e removê-los:

  ```bash
  uv run python -m app.maintenance prune-cvs           # só lista
  uv run python -m app.maintenance prune-cvs --apply   # remove
  ```

  Só são considerados arquivos gerados pelo CV Tailor; outros arquivos na pasta nunca são
  tocados. Se o banco não tiver nenhum CV registrado, o comando recusa remover e pede para
  conferir o `DATABASE_URL`.
- **Segurança:** a aplicação não tem login e aceita conexões só do próprio computador
  (`127.0.0.1`). Não altere isso para expô-la na rede.

## 9. Solução de problemas

**"Perfil não configurado. Preencha os dados em /settings/profile"**
O banco ainda não tem perfil. Preencha os **Dados gerais** no painel. As mensagens "Cadastre ao
menos uma competência" e "Cadastre ao menos uma experiência" pedem uma competência ativa (para o
match) e uma experiência ativa (para o CV).

**Editei o `profile.json` ou o `profile_base.json` e nada mudou**
Esperado: os arquivos só são importados na primeira execução, quando o banco ainda não tem
perfil. Edite o perfil em `/settings/profile`.

**O perfil não foi importado dos arquivos JSON**
A importação só acontece se o banco não tiver nenhum perfil. Arquivos ausentes ou inválidos são
ignorados: o log da subida mostra "Perfil não importado: …" com o motivo. Causas comuns:
`skills` vazio, `years_of_experience` negativo, data fora do formato `AAAA-MM`, ou um campo com o
nome digitado errado (por exemplo, `skils`). Corrija o arquivo e reinicie, ou cadastre o perfil
pelo painel.

**As análises aparecem como "sem LLM"**
O LLM não respondeu na hora da análise.
- **Ollama:** confira se está rodando (`curl http://localhost:11434/api/tags`) e se o modelo configurado
  (em `/settings/llm`, ou `OLLAMA_MODEL` no `.env`) aparece na lista. Se não aparecer, rode
  `ollama pull <modelo>`.
- **Gemini:** confira a chave e a quota no Google AI Studio.

Depois, clique em **Reanalisar**.

**"Falha de rede ao chamar o Ollama" ou "Ollama HTTP 404: model '…' not found"**
Ao gerar mensagens, o LLM é obrigatório: veja o item anterior.

**"GEMINI_API_KEY é obrigatória quando LLM_PROVIDER=gemini" ao iniciar**
Defina `GEMINI_API_KEY` no `.env`, ou volte para `LLM_PROVIDER=ollama`. Depois de subir, o
provedor e a chave também podem ser trocados no painel.

**"Nenhuma fonte respondeu"**
Todos os sites falharam, geralmente por bloqueio temporário. Espere alguns minutos, aumente o
delay mínimo e o máximo em `/settings/scrapers`, ou busque em menos sites.

**"Limite de N requisições por hora atingido. Tente novamente em X min…" (429)**
A busca ultrapassaria o limite por hora do painel. Espere o tempo indicado, escolha menos sites ou
aumente **Requisições por hora** em `/settings/scrapers` (`0` = sem limite). Se a busca sozinha
consultar mais sites que o limite, a mensagem pede para escolher menos plataformas.

**"Nenhuma das plataformas escolhidas está ativa" (422)**
Os sites pedidos estão desativados. Ative-os em `/settings/scrapers`.

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

**O painel recusa salvar uma experiência**
A página indica o campo. Causas comuns: data fora do formato `AAAA-MM`, término antes do início,
ou identificador repetido ou com espaços e maiúsculas.

**A análise ficou "sem LLM" ou o CV falha depois de editar um prompt**
O prompt personalizado provavelmente mudou o formato de resposta JSON. Clique em **Restaurar
padrão** em `/settings/llm`.

**"CV otimizado diverge do histórico: …"**
O LLM não conseguiu produzir um CV fiel ao histórico, mesmo após correção automática. Tente de
novo; se persistir, use um modelo maior ou o Gemini. A mensagem lista o que foi inventado.

**A otimização do CV excede o tempo limite**
Com o Ollama no processador, um CV leva de 1 a 3 minutos. Aumente `CV_LLM_TIMEOUT_SECONDS` se
necessário.

**"Requisição de outra origem bloqueada" (403)**
Proteção contra sites maliciosos. Use a aplicação pelo endereço `http://127.0.0.1:8000` e não
envie formulários a partir de outras páginas.
