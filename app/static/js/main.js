/*
 * Filmes & Séries — comportamento do front-end.
 * Tudo aqui é melhoria progressiva: sem JavaScript o site continua funcionando
 * (formulários fazem POST normal e os links levam às páginas completas).
 */
(() => {
  "use strict";

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ?? "";

  const debounce = (fn, wait) => {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  };

  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);

  /* Menu mobile ---------------------------------------------------------- */
  function initNav() {
    const toggle = document.querySelector("[data-nav-toggle]");
    const nav = document.querySelector("[data-nav]");
    if (!toggle || !nav) return;
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
      nav.classList.toggle("is-open", open);
    });
  }

  /* Menu da conta: fecha ao clicar fora ou apertar Esc -------------------- */
  function initAccountMenu() {
    const menu = document.querySelector("[data-menu]");
    if (!menu) return;
    document.addEventListener("click", (event) => {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menu.open) {
        menu.open = false;
        menu.querySelector("summary").focus();
      }
    });
  }

  /* Busca com autocompletar (usa GET /api/v1/search) ---------------------- */
  function initSearch() {
    const form = document.querySelector("[data-search]");
    const input = form?.querySelector("[data-search-input]");
    const list = form?.querySelector("[data-suggestions]");
    if (!form || !input || !list) return;

    let active = -1;
    let controller;

    const options = () => [...list.querySelectorAll('[role="option"]')];

    const close = () => {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    };

    const highlight = (index) => {
      const items = options();
      items.forEach((item, i) => item.setAttribute("aria-selected", String(i === index)));
      active = index;
      if (items[index]) {
        input.setAttribute("aria-activedescendant", items[index].id);
        items[index].scrollIntoView({ block: "nearest" });
      }
    };

    const render = (results, query) => {
      const searchUrl = `${form.action}?query=${encodeURIComponent(query)}`;
      if (!results.length) {
        list.innerHTML = `<li class="suggestions-empty">Nada encontrado para “${escapeHtml(query)}”.</li>`;
      } else {
        list.innerHTML = results.map((item, i) => `
          <li class="suggestion" role="option" id="sugestao-${i}" aria-selected="false">
            <a href="${escapeHtml(item.url)}" tabindex="-1">
              ${item.poster ? `<img src="${escapeHtml(item.poster)}" alt="" loading="lazy">` : `<span class="suggestion-ph"></span>`}
              <span><strong>${escapeHtml(item.title)}</strong>
              <span>${item.kind === "movie" ? "Filme" : "Série"}${item.year ? ` · ${item.year}` : ""}</span></span>
            </a>
          </li>`).join("") +
          `<li class="suggestion suggestions-all" role="option" id="sugestao-todos" aria-selected="false">
             <a href="${escapeHtml(searchUrl)}" tabindex="-1">Ver todos os resultados</a>
           </li>`;
      }
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      active = -1;
    };

    const fetchSuggestions = debounce(async () => {
      const query = input.value.trim();
      if (query.length < 2) return close();
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch(`/api/v1/search?q=${encodeURIComponent(query)}&limit=6`, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return close();
        const data = await response.json();
        if (input.value.trim() === query) render(data.results, query);
      } catch (error) {
        if (error.name !== "AbortError") close();
      }
    }, 220);

    input.addEventListener("input", fetchSuggestions);
    input.addEventListener("keydown", (event) => {
      const items = options();
      if (list.hidden || !items.length) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        highlight((active + 1) % items.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        highlight((active - 1 + items.length) % items.length);
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        window.location.href = items[active].querySelector("a").href;
      } else if (event.key === "Escape") {
        close();
      }
    });
    document.addEventListener("click", (event) => {
      if (!form.contains(event.target)) close();
    });
  }

  /* Favoritos sem recarregar a página (POST/DELETE /api/v1/favorites) ----- */
  function initFavorites() {
    document.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-favorite]");
      if (!button) return;
      event.preventDefault();
      const favorited = button.getAttribute("aria-pressed") === "true";
      button.disabled = true;
      try {
        const response = await fetch(`/api/v1/favorites/${button.dataset.kind}/${button.dataset.id}`, {
          method: favorited ? "DELETE" : "POST",
          headers: { "X-CSRFToken": csrfToken, Accept: "application/json" },
          credentials: "same-origin",
        });
        if (response.status === 401) {
          window.location.href = `/auth/login?next=${encodeURIComponent(location.pathname)}`;
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        button.setAttribute("aria-pressed", String(data.favorited));
      } catch {
        // Se a API falhar, cai no envio normal do formulário.
        button.closest("form")?.submit();
      } finally {
        button.disabled = false;
      }
    });
  }

  /* Trailer: só carrega o player do YouTube quando a pessoa clica ---------- */
  function initTrailers() {
    document.querySelectorAll("[data-trailer]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const iframe = document.createElement("iframe");
        iframe.src = link.dataset.src;
        iframe.title = link.dataset.title;
        iframe.allow = "accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen";
        iframe.allowFullscreen = true;
        iframe.referrerPolicy = "strict-origin-when-cross-origin";
        const wrapper = document.createElement("div");
        wrapper.className = "trailer";
        wrapper.append(iframe);
        link.replaceWith(wrapper);
        iframe.focus();
      });
    });
  }

  /* Fileiras horizontais com botões de rolagem ----------------------------- */
  function initRails() {
    document.querySelectorAll("[data-rail]").forEach((rail) => {
      const track = rail.querySelector("[data-rail-track]");
      const prev = rail.querySelector("[data-rail-prev]");
      const next = rail.querySelector("[data-rail-next]");
      if (!track || !prev || !next) return;

      const update = () => {
        const max = track.scrollWidth - track.clientWidth - 2;
        prev.disabled = track.scrollLeft <= 2;
        next.disabled = track.scrollLeft >= max;
        rail.querySelector(".rail-controls").hidden = max <= 0;
      };
      const scroll = (direction) => track.scrollBy({ left: direction * track.clientWidth * 0.85, behavior: "smooth" });

      prev.addEventListener("click", () => scroll(-1));
      next.addEventListener("click", () => scroll(1));
      track.addEventListener("scroll", debounce(update, 60), { passive: true });
      window.addEventListener("resize", debounce(update, 150));
      update();
    });
  }

  /* Filtros que se aplicam sozinhos ao trocar o select -------------------- */
  function initAutosubmit() {
    document.querySelectorAll("form[data-autosubmit]").forEach((form) => {
      form.querySelector("[data-autosubmit-button]")?.setAttribute("hidden", "");
      form.addEventListener("change", () => {
        // Remove campos vazios para a URL ficar limpa (ex.: ?sort=rating em vez de ?genre=&sort=rating)
        form.querySelectorAll("select").forEach((select) => { select.disabled = !select.value; });
        form.submit();
      });
    });
  }

  /* Confirmação antes de excluir (substitui o onsubmit inline, bloqueado pela CSP) */
  function initConfirmations() {
    document.addEventListener("submit", (event) => {
      const message = event.target.dataset?.confirm;
      if (message && !window.confirm(message)) event.preventDefault();
    });
  }

  /* Feedback em botões de ações demoradas (ex.: importar do TMDb) --------- */
  function initLoadingButtons() {
    document.addEventListener("submit", (event) => {
      const button = event.target.querySelector("[data-loading-text]");
      if (!button || event.defaultPrevented) return;
      button.disabled = true;
      button.textContent = button.dataset.loadingText;
    });
  }

  /* Avisos (flash) com botão de fechar ------------------------------------ */
  function initFlashes() {
    document.querySelectorAll("[data-flash-close]").forEach((button) => {
      button.addEventListener("click", () => button.closest("[data-flash]").remove());
    });
  }

  initNav();
  initAccountMenu();
  initSearch();
  initFavorites();
  initTrailers();
  initRails();
  initAutosubmit();
  initConfirmations();
  initLoadingButtons();
  initFlashes();
})();
