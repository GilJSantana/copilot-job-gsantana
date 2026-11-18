Atue como Engenheiro de Software Fullstack Sênior especialista em FastAPI, Python e integração com LLMs.

Na funcionalidade de **Match de Competências** da tela de detalhes da vaga, as skills exigidas pela vaga não estão sendo listadas na coluna "FALTANTES", exibindo a mensagem de que a vaga não lista skills estruturadas.

Por favor, implemente as seguintes melhorias para estruturar e cruzar as competências corretamente:

### 1. Atualização do Adaptador de IA (`app/adapters/gemini_adapter.py` / ILLMProvider):
- Ajuste o prompt enviado ao Gemini para que, além do `match_score`, `strengths`, e `gaps`, a IA retorne obrigatoriamente um campo adicional no JSON chamado `job_skills` contendo uma lista limpa e normalizada das hard skills exigidas na descrição da vaga (ex: `["Python", "SQL", "ETL", "Linux", "POO", "Docker"]`).

### 2. Ajuste no Serviço de Match e DTOs (`app/services/` ou rotas da API):
- Garanta que o endpoint de detalhes da vaga processe e retorne para o frontend:
  1. `profile_skills`: As competências do candidato.
  2. `job_skills`: As competências extraídas da vaga pelo LLM.
  3. `matched_skills` (Atendidas): Intersecção entre perfil e vaga.
  4. `missing_skills` (Faltantes): Skills da vaga ausentes no perfil.
  5. `extra_skills` (Só no Perfil): Skills do perfil não exigidas na vaga.

### 3. Ajuste no Frontend / Template:
- Atualize o componente de exibição do **Match de Competências** para iterar sobre o array real de `missing_skills` (`Faltantes`), exibindo-as como badges vermelhos em vez da mensagem estática atual.

Por favor, revise os arquivos correspondentes e aplique essa melhoria mantendo o padrão arquitetural do projeto.
