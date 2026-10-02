Atue como Engenheiro de Frontend Sênior e Especialista em UI/UX.

Nosso objetivo é implementar a Interface Web da página de busca de vagas para o projeto **copilot-job-gil** utilizando o design e os padrões de componentes do **TailAdmin (Tailwind CSS)**.

### 1. Diretrizes de Arquitetura & Componentização
- Adote uma arquitetura de componentes limpa e desacoplada em camadas:
  - `components/layout/`: Layout base, Header e Main Container.
  - `components/search/`: SearchPanel, InputGroups, PlatformChips, AdvancedFilters.
  - `components/jobs/`: JobCard, ResultsList, JobSkeleton, EmptyState.
  - `components/ui/`: Botões, Inputs, Badges e Switches base reutilizáveis com estilo TailAdmin.
- Utilize CSS utilitário Tailwind mantendo compatibilidade com o padrão visual do TailAdmin (estética limpa, modo claro/escuro nativo, sombras suaves `shadow-1`, bordas discretas `border-stroke`).

### 2. Hierarquia e Layout da Página (`Copilot Job Search`)

❖ Page Layout (`CopilotJobSearch`)
 └── ❖ Header (`Header.tsx` ou template equivalente)
 │    ├── Brand/Logo ("copilot-job-gil")
 │    └── Navigation Links ("Vagas", "Modelos de CV", "Configurações API")
 └── ❖ Main Container (`max-w-6xl mx-auto px-4 py-8`)
      ├── ❖ Search Panel (`bg-white dark:bg-boxdark rounded-sm border border-stroke p-6 shadow-default mb-6`)
      │    ├── Header do Card ("Buscar Oportunidades")
      │    ├── Grid de Inputs Primários (`grid grid-cols-1 md:grid-cols-2 gap-4`)
      │    │    ├── InputGroup: Cargo / Palavra-chave (ex: "Senior Python Engineer")
      │    │    └── InputGroup: Localização (ex: "São Paulo, Brasil")
      │    ├── Seção de Plataformas e Filtros Rápido (`flex flex-wrap gap-2 my-4`)
      │    │    ├── PlatformChips Toggle (LinkedIn, Indeed, Glassdoor)
      │    │    └── Remote Toggle Switch ("Apenas Remoto")
      │    ├── Accordion/Collapsible de Filtros Avançados
      │    │    ├── NumericControl: Limite de vagas (ex: 20)
      │    │    └── NumericControl: Vagas publicadas nas últimas X horas (ex: 24h)
      │    └── Primary Button ("Buscar Vagas" com ícone de lupa)
      └── ❖ Results Section
           ├── Subheader (`flex justify-between items-center mb-4`)
           │    ├── Section Title ("5 vagas encontradas")
           │    └── Sort Select ("Ordenar por: Aderência / Data")
           └── Stack (`space-y-4`)
                ├── State Condition:
                │    ├── [Loading]: 3x Skeleton Cards com efeito pulse
                │    ├── [Empty]: Ilustração/Mensagem "Nenhuma vaga encontrada"
                │    └── [Success]: Lista de JobCards
                └── ❖ Job Card (Componente individual)
                     ├── Header: Título da Vaga + Badge de Match Score (ex: "88% Match")
                     ├── Meta Info: Nome da Empresa | Localização | Publicada há Xh
                     ├── Tags: Badges para [Remoto], [Sênior], [Python]
                     └── Actions Bar:
                          ├── Secondary Button ("Copiar Pitch")
                          ├── Primary Button ("Ver Detalhes")
                          └── Action Button ("Otimizar CV para esta Vaga")

### 3. Tarefas de Implementação
1. Crie ou configure os componentes reutilizáveis utilizando a paleta de cores e o estilo do TailAdmin.
2. Certifique-se de que a página seja completamente responsiva (Mobile-first ou adaptável de `sm` a `xl`).
3. Monte o estado simulado (Mock Data) de 3 a 5 vagas com scores de match variados para validação visual.
4. Mantenha os eventos e manipuladores de estado (`onSearch`, `onFilterChange`, `onOptimizeCV`) prontos para integração com a API FastAPI do backend.

Pode proceder com a implementação da estrutura e dos componentes UI!