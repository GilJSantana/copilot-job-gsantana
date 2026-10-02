// Painel de configurações: só aprimoramentos — sem JS os formulários funcionam igual.
(() => {
  "use strict";

  function bindNumericSteppers() {
    document.querySelectorAll("[data-numeric]").forEach((group) => {
      const input = group.querySelector("input");
      group.querySelectorAll("[data-step]").forEach((stepper) => {
        stepper.addEventListener("click", () => {
          if (input.value === "") input.value = input.min || "0";
          else if (stepper.dataset.step === "1") input.stepUp();
          else input.stepDown();
        });
      });
    });
  }

  function bindThemeToggle() {
    const root = document.documentElement;
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const dark = root.classList.toggle("dark");
        try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* modo privado */ }
      });
    });
  }

  // remoções e restaurações pedem confirmação (data-confirm="mensagem")
  function bindConfirmations() {
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
      });
    });
  }

  // destaca os campos do provedor escolhido
  function bindProviderChoice() {
    const radios = document.querySelectorAll("input[name=provider]");
    const sync = () => {
      const chosen = document.querySelector("input[name=provider]:checked");
      document.querySelectorAll("[data-provider-fields]").forEach((fields) => {
        fields.classList.toggle("opacity-60", chosen && fields.dataset.providerFields !== chosen.value);
      });
    };
    radios.forEach((radio) => radio.addEventListener("change", sync));
    sync();
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindNumericSteppers();
    bindThemeToggle();
    bindConfirmations();
    bindProviderChoice();
  });
})();
