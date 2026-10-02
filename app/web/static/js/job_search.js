// Página de busca de vagas: handlers de estado sobre o HTML renderizado no servidor.
// Tudo aqui é aprimoramento — sem JS a busca e a navegação continuam funcionando.
(() => {
  "use strict";

  const SORT_KEY = "jobs.sort";

  const storage = {
    get(key) {
      try { return localStorage.getItem(key); } catch { return null; }
    },
    set(key, value) {
      try { localStorage.setItem(key, value); } catch { /* modo privado: só não lembra */ }
    },
  };

  async function apiRequest(method, path, body) {
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data && typeof data.detail === "string" ? data.detail : `erro ${response.status}`;
      throw new Error(detail);
    }
    return data;
  }

  // Mostra o progresso no próprio botão e devolve uma função que restaura o rótulo.
  function setBusy(button, text) {
    const label = button.querySelector("[data-label]") || button;
    const original = label.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    label.textContent = text;
    return (finalText, delayMs = 0) => {
      if (finalText) label.textContent = finalText;
      setTimeout(() => {
        label.textContent = original;
        button.disabled = false;
        button.removeAttribute("aria-busy");
      }, delayMs);
    };
  }

  function toast(message, tone = "danger") {
    const tones = {
      danger: "border-meta-1 text-meta-1",
      success: "border-meta-3 text-meta-3",
    };
    const el = document.createElement("div");
    el.setAttribute("role", tone === "danger" ? "alert" : "status");
    el.className = `fixed right-4 bottom-4 left-4 z-50 rounded-sm border-l-4 bg-white px-4 py-3 text-sm shadow-default sm:left-auto sm:max-w-sm dark:bg-boxdark ${tones[tone]}`;
    el.textContent = message;
    document.body.append(el);
    setTimeout(() => el.remove(), 6000);
  }

  const CopilotJobSearch = {
    // Busca: o POST /search é feito pelo próprio <form>; aqui só entra o estado [Loading].
    onSearch(form) {
      const button = form.querySelector("button[type=submit]");
      if (button) setBusy(button, form.dataset.busy || "Buscando…");
      const stack = document.querySelector("[data-results-stack]");
      const template = document.querySelector("[data-loading-template]");
      if (stack && template) stack.replaceChildren(template.content.cloneNode(true));
    },

    // Filtros do cliente: hoje, a ordenação dos cards já carregados.
    // Os filtros do formulário (sites, remoto…) só valem na próxima busca.
    onFilterChange({ sort } = {}) {
      const select = document.querySelector("[data-sort]");
      const order = sort || (select && select.value) || "date";
      if (select) {
        select.value = order;
        storage.set(SORT_KEY, order);
      }
      const stack = document.querySelector("[data-results-stack]");
      if (!stack) return;
      const cards = [...stack.querySelectorAll("[data-job-card]")];
      const key = order === "score"
        ? (card) => Number(card.dataset.score)
        : (card) => card.dataset.posted || "";
      // sort é estável: empates mantêm a ordem do servidor
      cards.sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0));
      stack.append(...cards);
    },

    // Gera um CV otimizado (POST /api/jobs/{key}/cvs) e abre a seção de CVs da vaga.
    async onOptimizeCV(jobKey, button) {
      const done = setBusy(button, "Gerando CV… pode levar minutos");
      try {
        await apiRequest("POST", `/api/jobs/${encodeURIComponent(jobKey)}/cvs`, { language: "pt" });
        done("CV gerado!");
        window.location.assign(`/jobs/${encodeURIComponent(jobKey)}#cv`);
      } catch (error) {
        done();
        toast(`Não foi possível otimizar o CV: ${error.message}`);
      }
    },

    // Copia o rascunho mais recente para o recrutador; sem nenhum, gera um convite do LinkedIn.
    async onCopyPitch(jobKey, button) {
      const base = `/api/jobs/${encodeURIComponent(jobKey)}/outreach`;
      const done = setBusy(button, "Preparando…");
      try {
        const drafts = await apiRequest("GET", base);
        const draft = drafts[0] || await apiRequest("POST", base, { channel: "linkedin_connection", language: "pt" });
        await navigator.clipboard.writeText(draft.body);
        done("Copiado!", 1500);
      } catch (error) {
        done();
        toast(`Não foi possível copiar o pitch: ${error.message}`);
      }
    },
  };

  function bindNumericSteppers(root) {
    root.querySelectorAll("[data-numeric]").forEach((group) => {
      const input = group.querySelector("input");
      group.querySelectorAll("[data-step]").forEach((stepper) => {
        stepper.addEventListener("click", () => {
          if (input.value === "") input.value = input.min || "0";
          else if (stepper.dataset.step === "1") input.stepUp();
          else input.stepDown();
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });
      });
    });
  }

  function bindThemeToggle() {
    const root = document.documentElement;
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const dark = root.classList.toggle("dark");
        storage.set("theme", dark ? "dark" : "light");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-search-form]");
    if (form) {
      form.addEventListener("submit", () => CopilotJobSearch.onSearch(form));
      bindNumericSteppers(form);
    }

    const select = document.querySelector("[data-sort]");
    if (select) {
      select.addEventListener("change", () => CopilotJobSearch.onFilterChange());
      const saved = storage.get(SORT_KEY);
      if (saved && saved !== select.value) CopilotJobSearch.onFilterChange({ sort: saved });
    }

    // delegação: um listener para todos os cards, inclusive os reordenados
    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      const card = button && button.closest("[data-job-card]");
      if (!card || button.disabled) return;
      if (button.dataset.action === "optimize-cv") CopilotJobSearch.onOptimizeCV(card.dataset.jobKey, button);
      if (button.dataset.action === "copy-pitch") CopilotJobSearch.onCopyPitch(card.dataset.jobKey, button);
    });

    bindThemeToggle();
  });

  window.CopilotJobSearch = CopilotJobSearch;
})();
