(function () {
  "use strict";

  const THEME_KEY = "dailynews-theme";
  const PAGE_SIZE = 20;
  const DEFAULT_TOPICS = [
    "Con người",
    "Tình yêu",
    "Sự nghiệp",
    "Đối nhân xử thế",
    "Tiền bạc",
    "Tâm lý",
    "Tư duy & khoa học",
    "Stoicism",
  ];

  const basePath =
    document.documentElement.dataset.base ||
    (location.pathname.includes("/DailyNews/")
      ? "/DailyNews/"
      : "/");

  function assetVersion() {
    return document.documentElement.dataset.assetVersion || "";
  }

  function asset(path) {
    const p = path.replace(/^\//, "");
    let url = basePath + p;
    const v = assetVersion();
    if (v && (p === "slow-reads/articles/index.json" || p.startsWith("slow-reads/articles/"))) {
      url += (url.includes("?") ? "&" : "?") + "v=" + encodeURIComponent(v);
    }
    return url;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function removeDiacritics(s) {
    return String(s)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D");
  }

  function normSearch(s) {
    return removeDiacritics(s).toLowerCase().replace(/\s+/g, " ").trim();
  }

  function effectiveTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "dark" || stored === "light") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(theme) {
    if (theme === "dark") document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
  }

  function updateThemeButton() {
    const btn = document.getElementById("btn-theme");
    if (!btn) return;
    const dark = effectiveTheme() === "dark";
    btn.setAttribute(
      "aria-label",
      dark
        ? "Đang dùng giao diện tối, bật chuyển sang sáng"
        : "Đang dùng giao diện sáng, bật chuyển sang tối"
    );
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
  }

  function initThemeToggle() {
    applyTheme(effectiveTheme());
    updateThemeButton();
    document.getElementById("btn-theme")?.addEventListener("click", () => {
      const next = effectiveTheme() === "dark" ? "light" : "dark";
      localStorage.setItem(THEME_KEY, next);
      applyTheme(next);
      updateThemeButton();
    });
  }

  function initMobileChrome() {
    const moreBtn = document.getElementById("btn-more");
    const menu = document.getElementById("more-menu");
    if (!moreBtn || !menu) return;
    const close = () => {
      menu.hidden = true;
      moreBtn.setAttribute("aria-expanded", "false");
    };
    moreBtn.addEventListener("click", () => {
      const open = menu.hidden;
      menu.hidden = !open;
      moreBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    menu.querySelector(".more-menu-backdrop")?.addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !menu.hidden) close();
    });
  }

  function parsePageParam() {
    const raw = parseInt(new URLSearchParams(location.search).get("page") || "1", 10);
    return Number.isFinite(raw) && raw >= 1 ? raw : 1;
  }

  function parseTopicParam() {
    return new URLSearchParams(location.search).get("topic") || "";
  }

  function parseQueryParam() {
    return new URLSearchParams(location.search).get("q") || "";
  }

  function listHref({ page, topic, q } = {}) {
    const params = new URLSearchParams();
    const t = topic !== undefined ? topic : parseTopicParam();
    const query = q !== undefined ? q : parseQueryParam();
    const p = page !== undefined ? page : parsePageParam();
    if (t) params.set("topic", t);
    if (query) params.set("q", query);
    if (p > 1) params.set("page", String(p));
    const qs = params.toString();
    return location.pathname + (qs ? "?" + qs : "");
  }

  function articleHref(id) {
    return asset(`slow-reads/article.html?id=${encodeURIComponent(id)}`);
  }

  function filterArticles(articles, topic, q) {
    const nq = normSearch(q);
    return articles.filter((a) => {
      if (topic && !(a.topics || []).includes(topic)) return false;
      if (!nq) return true;
      const hay = normSearch(
        [a.title, a.title_original, a.author, a.source, a.summary, ...(a.topics || [])].join(" ")
      );
      return nq.split(/\s+/).every((term) => hay.includes(term));
    });
  }

  function topicChips(active, allTopics, onSelect) {
    const wrap = document.getElementById("doc-cham-filters");
    if (!wrap) return;
    const chips = [{ id: "", label: "Tất cả" }, ...allTopics.map((t) => ({ id: t, label: t }))];
    wrap.innerHTML = `<div class="tag-chips-scroll"><div class="tag-chips archive-type-chips" role="list">${chips
      .map(
        ({ id, label }) =>
          `<button type="button" role="listitem" class="${active === id ? "active" : ""}" data-topic="${escapeHtml(id)}" aria-pressed="${active === id ? "true" : "false"}">${escapeHtml(label)}</button>`
      )
      .join("")}</div></div>`;
    wrap.querySelectorAll("[data-topic]").forEach((btn) => {
      btn.addEventListener("click", () => onSelect(btn.getAttribute("data-topic") || ""));
    });
  }

  function pageNumbers(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = new Set([1, total, current]);
    for (let d = -1; d <= 1; d += 1) {
      const p = current + d;
      if (p >= 1 && p <= total) pages.add(p);
    }
    const sorted = [...pages].sort((a, b) => a - b);
    const out = [];
    for (let i = 0; i < sorted.length; i += 1) {
      if (i > 0 && sorted[i] - sorted[i - 1] > 1) out.push(null);
      out.push(sorted[i]);
    }
    return out;
  }

  function renderPagination(currentPage, totalPages) {
    let nav = document.getElementById("doc-cham-pagination");
    if (!nav) {
      nav = document.createElement("nav");
      nav.id = "doc-cham-pagination";
      nav.className = "archive-pagination";
      nav.setAttribute("aria-label", "Phân trang Slow Reads");
    }
    if (totalPages <= 1) {
      nav.hidden = true;
      nav.innerHTML = "";
      return nav;
    }
    nav.hidden = false;
    const prevDisabled = currentPage <= 1;
    const nextDisabled = currentPage >= totalPages;
    const nums = pageNumbers(currentPage, totalPages)
      .map((p) => {
        if (p === null) {
          return `<span class="archive-page-ellipsis" aria-hidden="true">…</span>`;
        }
        if (p === currentPage) {
          return `<span class="archive-page-current" aria-current="page">${p}</span>`;
        }
        return `<a class="archive-page-link" href="${escapeHtml(listHref({ page: p }))}" data-page="${p}">${p}</a>`;
      })
      .join("");
    nav.innerHTML = `
      <a class="archive-page-nav${prevDisabled ? " is-disabled" : ""}" href="${prevDisabled ? "#" : escapeHtml(listHref({ page: currentPage - 1 }))}" data-page="${currentPage - 1}" aria-label="Trang trước"${prevDisabled ? ' aria-disabled="true" tabindex="-1"' : ""}>← Trước</a>
      <div class="archive-page-nums" role="group" aria-label="Số trang">${nums}</div>
      <a class="archive-page-nav${nextDisabled ? " is-disabled" : ""}" href="${nextDisabled ? "#" : escapeHtml(listHref({ page: currentPage + 1 }))}" data-page="${currentPage + 1}" aria-label="Trang sau"${nextDisabled ? ' aria-disabled="true" tabindex="-1"' : ""}>Sau →</a>`;
    return nav;
  }

  function cardHtml(a) {
    const topics = (a.topics || [])
      .map((t) => `<span class="ui-chip ui-chip--plain">${escapeHtml(t)}</span>`)
      .join("");
    const byline = [a.author, a.source].filter(Boolean).join(" · ");
    const mins = a.reading_minutes
      ? `<span class="doc-cham-card-mins">${escapeHtml(String(a.reading_minutes))} phút đọc</span>`
      : "";
    return `<article class="doc-cham-card">
      <h2 class="doc-cham-card-title"><a href="${escapeHtml(articleHref(a.id))}">${escapeHtml(a.title)}</a></h2>
      ${a.summary ? `<p class="doc-cham-card-summary">${escapeHtml(a.summary)}</p>` : ""}
      <p class="doc-cham-card-byline">${escapeHtml(byline)}${mins ? " · " + mins : ""}</p>
      ${topics ? `<div class="doc-cham-card-topics">${topics}</div>` : ""}
    </article>`;
  }

  async function initList() {
    initThemeToggle();
    initMobileChrome();
    const listEl = document.getElementById("doc-cham-list");
    const emptyEl = document.getElementById("doc-cham-empty");
    const statusEl = document.getElementById("doc-cham-status");
    const searchInput = document.getElementById("doc-cham-search");
    if (!listEl) return;

    const res = await fetch(asset("slow-reads/articles/index.json"), { cache: "no-cache" });
    if (!res.ok) throw new Error("Không tải được danh mục Slow Reads");
    const index = await res.json();
    const articles = index.articles || [];
    const topicSet = new Set([...(index.topics || []), ...DEFAULT_TOPICS]);
    articles.forEach((a) => (a.topics || []).forEach((t) => topicSet.add(t)));
    const allTopics = [
      ...DEFAULT_TOPICS.filter((t) => topicSet.has(t)),
      ...[...topicSet].filter((t) => !DEFAULT_TOPICS.includes(t)).sort(),
    ];

    if (searchInput) searchInput.value = parseQueryParam();

    function render() {
      const topic = parseTopicParam();
      const q = parseQueryParam();
      const filtered = filterArticles(articles, topic, q);
      const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
      let page = Math.min(Math.max(1, parsePageParam()), totalPages);
      if (page !== parsePageParam()) {
        history.replaceState(null, "", listHref({ page, topic, q }));
      }

      topicChips(topic, allTopics, (next) => {
        history.pushState(null, "", listHref({ page: 1, topic: next, q: parseQueryParam() }));
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });

      if (statusEl) {
        statusEl.textContent = filtered.length
          ? `${filtered.length} bài`
          : "Không có bài nào khớp.";
      }
      if (emptyEl) {
        emptyEl.hidden = filtered.length > 0;
        emptyEl.textContent = filtered.length
          ? ""
          : q || topic
            ? "Không có bài nào khớp bộ lọc hoặc tìm kiếm."
            : "Thư viện Slow Reads chưa có bài.";
      }

      const start = (page - 1) * PAGE_SIZE;
      const slice = filtered.slice(start, start + PAGE_SIZE);
      listEl.innerHTML = slice.map(cardHtml).join("");

      const nav = renderPagination(page, totalPages);
      const existing = document.getElementById("doc-cham-pagination");
      if (existing) existing.replaceWith(nav);
      else listEl.insertAdjacentElement("afterend", nav);
    }

    if (!document.body.dataset.slowReadsBound) {
      document.body.dataset.slowReadsBound = "1";
      document.body.addEventListener("click", (e) => {
        const link = e.target.closest("#doc-cham-pagination [data-page]");
        if (!link || link.classList.contains("is-disabled")) return;
        e.preventDefault();
        const page = parseInt(link.dataset.page, 10);
        if (!Number.isFinite(page) || page < 1) return;
        history.pushState(null, "", listHref({ page }));
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      window.addEventListener("popstate", render);
      const form = document.getElementById("doc-cham-search-form");
      form?.addEventListener("submit", (e) => {
        e.preventDefault();
        const q = (searchInput?.value || "").trim();
        history.pushState(null, "", listHref({ page: 1, q, topic: parseTopicParam() }));
        render();
      });
      searchInput?.addEventListener("input", () => {
        const q = (searchInput.value || "").trim();
        history.replaceState(null, "", listHref({ page: 1, q, topic: parseTopicParam() }));
        render();
      });
    }

    render();
  }

  function renderBody(blocks) {
    return (blocks || [])
      .map((b) => {
        const type = b.type || "p";
        const text = b.text || "";
        if (type === "h2") return `<h2>${escapeHtml(text)}</h2>`;
        if (type === "h3") return `<h3>${escapeHtml(text)}</h3>`;
        if (type === "quote") {
          const cite = b.cite
            ? `<footer class="doc-cham-quote-cite">— ${escapeHtml(b.cite)}</footer>`
            : "";
          return `<blockquote class="doc-cham-quote"><p>${escapeHtml(text)}</p>${cite}</blockquote>`;
        }
        return `<p>${escapeHtml(text)}</p>`;
      })
      .join("");
  }

  async function initArticle() {
    initThemeToggle();
    initMobileChrome();
    const root = document.getElementById("slow-reads-article");
    const status = document.getElementById("status");
    if (!root) return;
    const id = new URLSearchParams(location.search).get("id") || "";
    if (!id) {
      if (status) {
        status.className = "error-msg";
        status.textContent = "Thiếu mã bài (id).";
      }
      return;
    }
    try {
      const res = await fetch(asset(`slow-reads/articles/${encodeURIComponent(id)}.json`), {
        cache: "no-cache",
      });
      if (!res.ok) throw new Error("Không tìm thấy bài này.");
      const a = await res.json();
      if (status) status.hidden = true;
      document.title = `${a.title} — Slow Reads — Daily News`;
      const translated = a.lang && a.lang !== "vi";
      const topics = (a.topics || [])
        .map((t) => `<span class="ui-chip ui-chip--plain">${escapeHtml(t)}</span>`)
        .join("");
      const sourceLink = a.source_url
        ? `<a class="source-link" href="${escapeHtml(a.source_url)}" rel="noopener noreferrer" target="_blank">${escapeHtml(a.source || a.source_url)}</a>`
        : escapeHtml(a.source || "");
      root.innerHTML = `
        <p class="doc-cham-back"><a href="${escapeHtml(asset("slow-reads/"))}">← Thư viện Slow Reads</a></p>
        <header class="doc-cham-article-head">
          <h1>${escapeHtml(a.title)}</h1>
          ${a.title_original ? `<p class="doc-cham-title-original">${escapeHtml(a.title_original)}</p>` : ""}
          <p class="doc-cham-article-byline">${escapeHtml(a.author || "")}${a.author && a.source ? " · " : ""}${sourceLink}${a.reading_minutes ? ` · ${escapeHtml(String(a.reading_minutes))} phút đọc` : ""}</p>
          ${translated ? `<p class="doc-cham-translated ui-chip ui-chip--accent">Bản dịch tiếng Việt</p>` : ""}
          ${topics ? `<div class="doc-cham-card-topics">${topics}</div>` : ""}
        </header>
        <div class="doc-cham-prose">${renderBody(a.body)}</div>
        <p class="doc-cham-back doc-cham-back-bottom"><a href="${escapeHtml(asset("slow-reads/"))}">← Thư viện Slow Reads</a></p>
      `;
    } catch (e) {
      if (status) {
        status.hidden = false;
        status.className = "error-msg";
        status.textContent = e.message || String(e);
      }
    }
  }

  if (document.body.dataset.page === "slow-reads") {
    initList().catch((e) => {
      const status = document.getElementById("doc-cham-status");
      if (status) {
        status.textContent = e.message || String(e);
        status.className = "error-msg";
      }
    });
  }
  if (document.body.dataset.page === "slow-reads-article") {
    initArticle();
  }
})();
