Atue como Engenheiro de Software Fullstack Sênior especialista em FastAPI, Tailwind CSS e arquitetura limpa.

Precisamos implementar melhorias cruciais na experiência do usuário (UX) e na lógica de busca e match do projeto **copilot-job-gil**. Por favor, execute as seguintes correções detalhadas abaixo:

---

### 1. Correção no Filtro de Localização por País (Apontamento 1)
- **Problema:** Quando o usuário informa apenas o nome do país no campo de localização (ex: "Brasil"), o sistema atualmente retorna oportunidades em diversos países.
- **Ação:**
  - Ajuste a camada de serviço/adaptador de busca (`python-jobspy` wrapper) para tratar corretamente quando a string de localização contiver apenas um país.
  - Garanta que o filtro geográfico seja estritamente aplicado ao país referenciado, normalizando a string de entrada caso necessário.

### 2. Persistência de Filtros de Busca na Navegação (Apontamento 2)
- **Problema:** Ao entrar na tela de detalhes de uma vaga e retornar para a listagem/busca, os valores digitados nos campos "Cargo" e "Localização" são apagados.
- **Ação:**
  - Sincronize o estado dos inputs de busca com os **Query Parameters da URL** (ex: usando `URLSearchParams` ou roteamento equivalente no frontend).
  - Garanta que ao navegar de volta da tela de detalhes (`/jobs/{id}`) para a busca, os parâmetros na URL sejam lidos e repovoados automaticamente nos inputs. Os filtros só devem ser limpos na inicialização limpa da aplicação ou se o usuário clicar explicitamente em um botão "Limpar Filtros".

### 3. Exibição Comparativa de Skills na Tela de Detalhes (Apontamento 3)
- **Problema:** A tela de detalhes da oportunidade exibe apenas as skills da vaga, ocultando as competências do currículo do usuário.
- **Ação:**
  - Atualize o componente de detalhes da vaga e o DTO/endpoint backend para retornar conjuntamente:
    1. As skills exigidas pela vaga.
    2. As skills do perfil do usuário (vindas do `ProfileCore` / banco de dados).
  - Na UI (TailAdmin), exiba uma seção visual de **Gap Analysis / Match de Competências**, destacando com cores diferentes as skills atendidas (match) e as skills faltantes (gaps) para facilitar a tomada de decisão do usuário.

Por favor, analise a estrutura atual do projeto e implemente essas melhorias mantendo os padrões SOLID e a compatibilidade com o design TailAdmin/Tailwind.