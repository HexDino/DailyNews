(function () {
  "use strict";

  const MASTHEAD = "Daily News";
  const FAV_KEY = "dailynews-favorites";
  const THEME_KEY = "dailynews-theme";
  const CALENDAR_OPEN_KEY = "dailynews-calendar-open";
  const ARCHIVE_PAGE_SIZE = 20;
  /** @type {{ version: string, entries: object[] } | null} */
  let searchIndexCache = null;
  const SEARCH_INDEX_KEY = "dailynews-search-index-version";
  const THU = [
    "Chủ Nhật",
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
  ];

  const TAGS = [
    { id: "all", label: "Tất cả" },
    { id: "tech", label: "Công nghệ" },
    { id: "construction", label: "Xây dựng" },
    { id: "football", label: "Bóng đá" },
    { id: "politics", label: "Chính trị" },
    { id: "culture", label: "Văn hoá" },
    { id: "lifestyle", label: "Đời sống" },
    { id: "ai", label: "AI / Trí tuệ nhân tạo" },
    { id: "github", label: "GitHub / Kho GitHub" },
  ];

  const MOBILE_NARROW_TAG_HIDE = new Set(["ai", "github"]);

  function isMobileLayout() {
    return window.matchMedia("(max-width: 640px)").matches;
  }

  function tagsForLayout() {
    if (isMobileLayout()) {
      return TAGS.filter((t) => !MOBILE_NARROW_TAG_HIDE.has(t.id));
    }
    return TAGS;
  }

  const SECTION_TAG = {
    "Trí tuệ nhân tạo": "ai",
    "Kho GitHub đáng chú ý": "github",
    "Bóng đá": "football",
    "Chính trị": "politics",
    "Văn hoá": "culture",
    "Đời sống": "lifestyle",
  };

  const EMPTY_TAG_COPY = {
    construction:
      "Số báo này chưa có mục Xây dựng. Các số sau có thể bổ sung tin với trường tags trong JSON.",
    culture:
      "Số báo này chưa có mục Văn hoá. Các số sau có thể bổ sung tin với trường tags trong JSON.",
    lifestyle:
      "Số báo này chưa có mục Đời sống. Các số sau có thể bổ sung tin với trường tags trong JSON.",
  };

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
    if (
      v &&
      (p === "issues/index.json" || p === "issues/search-index.json")
    ) {
      url += (url.includes("?") ? "&" : "?") + "v=" + encodeURIComponent(v);
    }
    return url;
  }

  function fetchJson(url) {
    return fetch(url, { cache: "no-cache" });
  }

  function vnDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    return `${THU[dt.getUTCDay()]}, ${d} tháng ${m}, ${y}`;
  }

  const CHIEU_SUFFIX = "-chieu";

  function parseIssueId(issueId) {
    if (issueId.endsWith(CHIEU_SUFFIX)) {
      return {
        issueId,
        calendarDate: issueId.slice(0, -CHIEU_SUFFIX.length),
        edition: "chieu",
      };
    }
    return { issueId, calendarDate: issueId, edition: null };
  }

  function calendarDateFromIssueId(issueId) {
    return parseIssueId(issueId).calendarDate;
  }

  function dayHasEveningEdition(index, calendarDate) {
    return index.issues.some(
      (i) =>
        calendarDateFromIssueId(i.date) === calendarDate &&
        parseIssueId(i.date).edition === "chieu"
    );
  }

  function issueListLabel(issueId, index) {
    const cal = calendarDateFromIssueId(issueId);
    const day = vnDate(cal);
    const { edition } = parseIssueId(issueId);
    const both = dayHasEveningEdition(index, cal);
    if (edition === "chieu") return `${day} · Buổi chiều`;
    if (both) return `${day} · Buổi sáng`;
    return day;
  }

  function removeDiacritics(s) {
    return String(s)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D");
  }

  function slugify(text) {
    return removeDiacritics(text)
      .toLowerCase()
      .replace(/&/g, " va ")
      .replace(/[^a-z0-9\s-]/g, "")
      .trim()
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-");
  }

  function topicSlug(topic) {
    return slugify(topic);
  }

  function sectionSlug(title) {
    return slugify(title);
  }

  function subsectionSlug(topic, subtitle) {
    return slugify(`${topic} ${subtitle}`);
  }

  function parseParams() {
    const q = new URLSearchParams(location.search);
    let date = q.get("date");
    let tag = q.get("tag") || "all";
    let searchQuery = q.get("q") || "";
    let anchor = "";
    const raw = location.hash.slice(1);
    if (raw.startsWith("tag=")) {
      if (!q.has("tag")) tag = raw.slice(4) || "all";
    } else if (raw) {
      anchor = decodeURIComponent(raw);
    }
    return { date, tag, anchor, searchQuery };
  }

  function syncUrl(date, tag, anchor, searchQuery) {
    const q = new URLSearchParams();
    if (date) q.set("date", date);
    if (tag && tag !== "all") q.set("tag", tag);
    if (searchQuery) q.set("q", searchQuery);
    const qs = q.toString();
    let url = location.pathname + (qs ? "?" + qs : "");
    if (anchor) url += "#" + encodeURIComponent(anchor);
    history.replaceState(null, "", url);
  }

  function normSearch(s) {
    return removeDiacritics(String(s)).toLowerCase();
  }

  function levenshteinMax(a, b, max) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    if (Math.abs(a.length - b.length) > max) return max + 1;
    const prev = new Array(b.length + 1);
    const curr = new Array(b.length + 1);
    for (let j = 0; j <= b.length; j++) prev[j] = j;
    for (let i = 1; i <= a.length; i++) {
      curr[0] = i;
      let rowMin = i;
      for (let j = 1; j <= b.length; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
        rowMin = Math.min(rowMin, curr[j]);
      }
      if (rowMin > max) return max + 1;
      for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
    }
    return prev[b.length];
  }

  function maxTypos(token) {
    if (token.length <= 2) return 0;
    if (token.length <= 4) return 1;
    return Math.max(1, Math.floor(token.length * 0.34));
  }

  function isSubsequence(needle, hay) {
    let i = 0;
    for (let j = 0; j < hay.length && i < needle.length; j++) {
      if (hay[j] === needle[i]) i += 1;
    }
    return i === needle.length;
  }

  function tokenMatchesInWords(token, words, fullText) {
    if (fullText.includes(token)) return { quality: 0 };
    for (const w of words) {
      if (!w) continue;
      if (w === token) return { quality: 0 };
      if (w.startsWith(token) || (token.length >= 3 && token.startsWith(w))) {
        return { quality: 0.05 };
      }
      if (token.length >= 3 && w.includes(token)) return { quality: 0.08 };
      if (token.length >= 4 && isSubsequence(token, w)) return { quality: 0.12 };
      const maxD = maxTypos(token);
      const d = levenshteinMax(token, w, maxD);
      if (d <= maxD) return { quality: 0.15 + d * 0.04 };
    }
    return null;
  }

  function wordMatchesToken(word, token) {
    const w = normSearch(word);
    if (!w || !token) return false;
    return !!tokenMatchesInWords(token, [w], w);
  }

  function scoreSearchRow(row, tokens) {
    const headlineWords = row.normHeadline.split(/[^a-z0-9]+/).filter(Boolean);
    const textWords = row.normText.split(/[^a-z0-9]+/).filter(Boolean);
    let score = 0;
    for (const token of tokens) {
      let m = tokenMatchesInWords(token, headlineWords, row.normHeadline);
      if (m) {
        score += 100 - m.quality * 20;
      } else {
        m = tokenMatchesInWords(token, textWords, row.normText);
        if (!m) return null;
        score += 30 - m.quality * 20;
      }
    }
    score += row.recencyRank * 0.001;
    return score;
  }

  function articleDomId(issueId, sec, itemIndex) {
    const secKey = sec.topic
      ? sec.subtitle
        ? subsectionSlug(sec.topic, sec.subtitle)
        : topicSlug(sec.topic)
      : sectionSlug(sec.title);
    return `art-${issueId}-${secKey}-${itemIndex}`;
  }

  function sectionLabel(sec) {
    if (sec.topic) {
      return sec.subtitle ? `${sec.topic} · ${sec.subtitle}` : sec.topic;
    }
    return sec.title || "";
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
      dark ? "Đang dùng giao diện tối, bật chuyển sang sáng" : "Đang dùng giao diện sáng, bật chuyển sang tối"
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

  function itemSearchText(item, sec) {
    const parts = [
      item.headline,
      item.meta,
      sec.title,
      sec.topic,
      sec.subtitle,
      sec.intro,
    ];
    if (item.body) {
      parts.push(...(Array.isArray(item.body) ? item.body : [item.body]));
    }
    (item.sources || []).forEach((s) => parts.push(s.name));
    return parts.filter(Boolean).join(" ");
  }

  function snippetForRow(row, terms) {
    const source = row.snippetSource || row.headline || "";
    const max = 160;
    let slice = source.slice(0, max);
    if (source.length > max) slice += "…";
    const normSlice = normSearch(slice);
    let start = 0;
    for (const term of terms) {
      const i = normSlice.indexOf(term);
      if (i >= 0) {
        start = Math.max(0, i - 40);
        break;
      }
    }
    if (start > 0) {
      slice = (start > 3 ? "…" : "") + source.slice(start, start + max);
      if (start + max < source.length) slice += "…";
    }
    return highlightTerms(slice, terms);
  }

  function highlightTerms(text, terms) {
    if (!terms.length) return escapeHtml(text);
    const parts = text.split(/(\s+)/);
    return parts
      .map((part) => {
        if (!part.trim()) return escapeHtml(part);
        const hit = terms.some((t) => wordMatchesToken(part, t));
        if (hit) return `<mark>${escapeHtml(part)}</mark>`;
        return escapeHtml(part);
      })
      .join("");
  }

  async function loadSearchIndex() {
    const res = await fetchJson(asset("issues/search-index.json"));
    if (!res.ok) throw new Error("Không tải được chỉ mục tìm kiếm");
    const data = await res.json();
    const prev = localStorage.getItem(SEARCH_INDEX_KEY);
    if (prev && prev !== data.version) searchIndexCache = null;
    localStorage.setItem(SEARCH_INDEX_KEY, data.version);
    searchIndexCache = data;
    return data;
  }

  async function ensureSearchCorpus() {
    if (searchIndexCache) return searchIndexCache.entries;
    const data = await loadSearchIndex();
    return data.entries;
  }

  function runSearch(query, corpus) {
    const trimmed = query.trim();
    if (!trimmed) return [];
    const terms = normSearch(trimmed).split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    const scored = [];
    corpus.forEach((row) => {
      const s = scoreSearchRow(row, terms);
      if (s !== null) scored.push({ row, score: s });
    });
    scored.sort((a, b) => b.score - a.score);
    return scored.map((x) => x.row);
  }

  function issueHref(issueId, articleId) {
    return `${asset("index.html")}?date=${encodeURIComponent(issueId)}#${encodeURIComponent(articleId)}`;
  }

  function initSearch(indexRef) {
    const form = document.getElementById("search-form");
    const input = document.getElementById("search-input");
    const panel = document.getElementById("search-panel");
    const wrap = document.getElementById("search-wrap");
    const statusEl = document.getElementById("search-status");
    const listEl = document.getElementById("search-results");
    const closeBtn = document.getElementById("search-close");
    if (!form || !input || !panel || !listEl) return;

    let indexPromise = indexRef
      ? Promise.resolve(indexRef)
      : loadIndex();
    let debounceTimer = 0;
    let searchGen = 0;

    const searchOpenBtn = document.getElementById("btn-search-open");
    const searchDrawerClose = document.getElementById("search-drawer-close");

    function setSearchDrawerOpen(open) {
      document.body.classList.toggle("search-drawer-open", open);
      searchOpenBtn?.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function setPanelOpen(open) {
      panel.hidden = !open;
      input.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function closeSearch(clearInput) {
      setPanelOpen(false);
      setSearchDrawerOpen(false);
      if (clearInput) input.value = "";
      const { date, tag, anchor } = parseParams();
      syncUrl(date, tag, anchor, "");
    }

    function openSearchDrawer() {
      setSearchDrawerOpen(true);
      window.setTimeout(() => input.focus(), 0);
    }

    async function showResults(query, pushUrl) {
      const q = query.trim();
      if (input.value !== q) input.value = q;
      if (!q) {
        closeSearch(false);
        return;
      }
      setPanelOpen(true);
      if (isMobileLayout()) setSearchDrawerOpen(true);
      statusEl.textContent = "Đang tìm…";
      listEl.innerHTML = "";
      const gen = ++searchGen;
      const index = await indexPromise;
      const corpus = await ensureSearchCorpus();
      if (gen !== searchGen) return;
      const hits = runSearch(q, corpus);
      const terms = normSearch(q).split(/\s+/).filter(Boolean);
      if (pushUrl) {
        const params = parseParams();
        syncUrl(params.date, params.tag, params.anchor, q);
      }
      if (!hits.length) {
        statusEl.textContent = `Không có kết quả cho “${q}”.`;
        return;
      }
      statusEl.textContent = `${hits.length} kết quả cho “${q}”.`;
      listEl.innerHTML = hits
        .slice(0, 80)
        .map((row) => {
          const label = issueListLabel(row.issueId, index);
          return `<li class="search-hit">
            <a class="search-hit-link" href="${issueHref(row.issueId, row.articleId)}">
              <span class="search-hit-meta">${escapeHtml(label)} · ${escapeHtml(row.section)}</span>
              <span class="search-hit-headline">${highlightTerms(row.headline, terms)}</span>
              <span class="search-hit-snippet">${snippetForRow(row, terms)}</span>
            </a>
          </li>`;
        })
        .join("");
    }

    function scheduleSearch(pushUrl) {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        showResults(input.value, pushUrl);
      }, 220);
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      window.clearTimeout(debounceTimer);
      showResults(input.value, true);
    });

    input.addEventListener("input", () => {
      if (!input.value.trim()) {
        window.clearTimeout(debounceTimer);
        closeSearch(false);
        return;
      }
      scheduleSearch(true);
    });

    input.addEventListener("focus", () => {
      if (input.value.trim()) setPanelOpen(true);
    });

    closeBtn?.addEventListener("click", () => closeSearch(true));
    searchDrawerClose?.addEventListener("click", () => closeSearch(true));
    searchOpenBtn?.addEventListener("click", () => {
      if (document.body.classList.contains("search-drawer-open")) {
        closeSearch(false);
      } else {
        openSearchDrawer();
        if (input.value.trim()) setPanelOpen(true);
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (document.body.classList.contains("search-drawer-open") || !panel.hidden) {
          e.preventDefault();
          closeSearch(false);
          input.blur();
        }
        if (document.body.classList.contains("more-menu-open")) {
          setMoreMenuOpen(false);
        }
      }
    });

    document.addEventListener("pointerdown", (e) => {
      if (panel.hidden && !document.body.classList.contains("search-drawer-open")) return;
      const t = e.target;
      if (wrap && t instanceof Node && wrap.contains(t)) return;
      if (searchOpenBtn && t instanceof Node && searchOpenBtn.contains(t)) return;
      if (!panel.hidden) closeSearch(false);
      else setSearchDrawerOpen(false);
    });

    const { searchQuery } = parseParams();
    if (searchQuery) {
      input.value = searchQuery;
      if (isMobileLayout()) openSearchDrawer();
      showResults(searchQuery, false);
    }
  }

  function setMoreMenuOpen(open) {
    if (!isMobileLayout()) return;
    const menu = document.getElementById("more-menu");
    const btn = document.getElementById("btn-more");
    if (!menu) return;
    menu.hidden = !open;
    document.body.classList.toggle("more-menu-open", open);
    btn?.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function syncMoreMenuLayout() {
    const menu = document.getElementById("more-menu");
    if (!menu) return;
    if (isMobileLayout()) {
      if (!document.body.classList.contains("more-menu-open")) menu.hidden = true;
    } else {
      menu.hidden = false;
      document.body.classList.remove("more-menu-open");
    }
  }

  function initMobileChrome() {
    const moreBtn = document.getElementById("btn-more");
    const menu = document.getElementById("more-menu");
    if (!moreBtn || !menu) return;

    syncMoreMenuLayout();
    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(syncMoreMenuLayout, 120);
    });

    moreBtn.addEventListener("click", () => {
      setMoreMenuOpen(menu.hidden);
    });
    menu.querySelector(".more-menu-backdrop")?.addEventListener("click", () => {
      setMoreMenuOpen(false);
    });
    menu.querySelectorAll(".actions a, .actions button").forEach((el) => {
      el.addEventListener("click", () => setMoreMenuOpen(false));
    });
    menu.querySelector(".more-menu-archive")?.addEventListener("click", () => {
      setMoreMenuOpen(false);
    });

    const strip = document.getElementById("tag-strip");
    if (!strip) return;
    let lastScrollY = window.scrollY;
    let scrollTick = false;
    window.addEventListener(
      "scroll",
      () => {
        if (!isMobileLayout()) {
          strip.classList.remove("tag-strip--hidden");
          return;
        }
        if (scrollTick) return;
        scrollTick = true;
        requestAnimationFrame(() => {
          const y = window.scrollY;
          if (y > lastScrollY && y > 72) strip.classList.add("tag-strip--hidden");
          else strip.classList.remove("tag-strip--hidden");
          lastScrollY = y;
          scrollTick = false;
        });
      },
      { passive: true }
    );
  }

  function injectIssuePager(root, prev, next) {
    root.querySelector(".issue-pager")?.remove();
    if (!prev && !next) return;
    const nav = document.createElement("nav");
    nav.className = "issue-pager";
    nav.setAttribute("aria-label", "Chuyển số báo");
    nav.innerHTML = `${prev ? `<a class="btn" href="${asset(`index.html?date=${prev}`)}">← Số trước</a>` : ""}${next ? `<a class="btn" href="${asset(`index.html?date=${next}`)}">Số sau →</a>` : ""}`;
    root.appendChild(nav);
  }

  function scrollToAnchor(id) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openCalendarFromToc(paper) {
    if (!paper?.querySelector("#lich-su-kien")) return;
    const panel = getCalendarPanel();
    if (!panel) return;
    if (useCalendarModal()) {
      setCalendarOpen(true, paper);
      return;
    }
    scrollToAnchor("lich-su-kien");
    setCalendarOpen(true, paper);
  }

  function getFavorites() {
    try {
      return JSON.parse(localStorage.getItem(FAV_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function setFavorites(dates) {
    localStorage.setItem(FAV_KEY, JSON.stringify([...new Set(dates)].sort().reverse()));
  }

  function toggleFavorite(date) {
    const fav = getFavorites();
    const i = fav.indexOf(date);
    if (i >= 0) fav.splice(i, 1);
    else fav.unshift(date);
    setFavorites(fav);
    return fav.includes(date);
  }

  function itemTags(item, section) {
    if (item.tags && item.tags.length) return item.tags;
    if (section.tags && section.tags.length) return section.tags;
    const t = SECTION_TAG[section.title];
    return t ? [t] : [];
  }

  function tagInList(list, tag) {
    if (!list || !list.length) return false;
    if (tag === "tech") {
      return list.some(
        (t) => t === "tech" || t === "ai" || t === "github"
      );
    }
    return list.includes(tag);
  }

  function sectionMatches(section, tag) {
    if (tag === "all") return true;
    if (tagInList(section.tags, tag)) return true;
    const legacy = SECTION_TAG[section.title];
    if (tag === "tech") return legacy === "ai" || legacy === "github";
    return legacy === tag;
  }

  function itemMatchesTag(item, section, tag) {
    return tagInList(itemTags(item, section), tag);
  }

  function filterSections(data, tag) {
    if (tag === "all") return data.sections;
    return data.sections
      .map((sec) => {
        if (!sectionMatches(sec, tag)) {
          const items = (sec.items || []).filter((it) =>
            itemMatchesTag(it, sec, tag)
          );
          if (!items.length) return null;
          return { ...sec, items };
        }
        const items = (sec.items || []).filter((it) =>
          itemMatchesTag(it, sec, tag)
        );
        return { ...sec, items };
      })
      .filter(Boolean);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bodyHtml(body) {
    const paras = Array.isArray(body) ? body : [body];
    return paras.map((p) => `<p>${escapeHtml(p)}</p>`).join("");
  }

  function sourceLinkDisplay(src) {
    const name = String(src.name || "").trim();
    const url = String(src.url || "").trim();
    if (url) {
      let label = name;
      if (!label) {
        try {
          label = new URL(url).hostname.replace(/^www\./i, "");
        } catch {
          label = url;
        }
      }
      return {
        label,
        url,
        title: url,
        hasLink: true,
      };
    }
    return { label: name, url: "", title: "", hasLink: false };
  }

  function sourcesHtml(sources) {
    if (!sources || !sources.length) return "";
    const parts = sources.map((src) => {
      const d = sourceLinkDisplay(src);
      if (d.hasLink) {
        return `<a class="source-link" href="${escapeHtml(d.url)}" title="${escapeHtml(d.title)}" rel="noopener noreferrer" target="_blank">${escapeHtml(d.label)}</a>`;
      }
      return escapeHtml(d.label);
    });
    const sep = '<span class="sources-sep" aria-hidden="true"> · </span>';
    return `<p class="sources-line"><span class="sources-label">Nguồn:</span> ${parts.join(sep)}</p>`;
  }

  function formatShortDate(iso) {
    const parts = String(iso || "").split("-");
    if (parts.length !== 3) return iso;
    return `${parts[2]}/${parts[1]}`;
  }

  function truncateText(text, maxLen) {
    const t = String(text || "").trim();
    if (t.length <= maxLen) return t;
    return `${t.slice(0, maxLen - 1).trimEnd()}…`;
  }

  function parseIsoDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  }

  function addDaysUtc(dt, days) {
    const n = new Date(dt.getTime());
    n.setUTCDate(n.getUTCDate() + days);
    return n;
  }

  function upcomingCalendarEvents(data, issueId, windowDays = 14) {
    const list = data.calendar || [];
    if (!list.length) return [];
    const start = parseIsoDate(calendarDateFromIssueId(issueId));
    const end = addDaysUtc(start, windowDays);
    return list
      .filter((ev) => {
        if (!ev.date) return false;
        const d = parseIsoDate(ev.date);
        return d >= start && d <= end;
      })
      .sort(
        (a, b) =>
          a.date.localeCompare(b.date) ||
          String(a.time || "").localeCompare(String(b.time || ""))
      );
  }

  function followupOriginMeta(firstIssue) {
    if (!firstIssue) return "";
    const cal = calendarDateFromIssueId(firstIssue);
    const parts = cal.split("-").map(Number);
    if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return "";
    const [, m, d] = parts;
    const label = `từ số ${d}/${m}`;
    return `<a class="followup-origin source-link" href="${asset("index.html")}?date=${encodeURIComponent(firstIssue)}">${escapeHtml(label)}</a>`;
  }

  function renderFollowups(followups) {
    if (!followups || !followups.length) return "";
    const items = followups
      .map((fu, idx) => {
        const status =
          fu.status === "đã kết thúc" ? "đã kết thúc" : "đang diễn biến";
        const statusClass =
          status === "đã kết thúc"
            ? "ui-chip--status-done"
            : "ui-chip--status-ongoing";
        const origin = followupOriginMeta(fu.first_issue);
        const first = fu.first_issue
          ? `<a class="source-link" href="${asset("index.html")}?date=${encodeURIComponent(fu.first_issue)}">Số ${escapeHtml(fu.first_issue)}</a>`
          : "";
        return `<li class="followup-row-wrap">
          <details class="followup-row" id="followup-${idx}">
            <summary class="followup-summary">
              <span class="ui-chip followup-status ${statusClass}">${escapeHtml(status)}</span>
              <span class="followup-title">${escapeHtml(fu.title || "")}</span>
              ${origin ? origin : ""}
              <p class="followup-preview">${escapeHtml(fu.update || "")}</p>
            </summary>
            <div class="followup-body">
              <p>${escapeHtml(fu.update || "")}</p>
              ${first ? `<p class="followup-first">Lần đầu: ${first}</p>` : ""}
              ${sourcesHtml(fu.sources)}
            </div>
          </details>
        </li>`;
      })
      .join("");
    return `<details class="followups-block" id="theo-doi-tin-cu">
      <summary><span class="followups-summary-label">Theo dõi tin cũ</span> <span class="followups-count">(${followups.length})</span></summary>
      <ul class="followups-list">${items}</ul>
      <p class="back-to-toc"><a class="toc-link" href="#muc-luc">↑ Mục lục</a></p>
    </details>`;
  }

  function isEventOnIssueDay(evDate, issueId) {
    return evDate === calendarDateFromIssueId(issueId);
  }

  function renderCalendarEventList(events, issueId) {
    let lastDate = "";
    return events
      .map((ev) => {
        let head = "";
        if (ev.date !== lastDate) {
          lastDate = ev.date;
          const today = isEventOnIssueDay(ev.date, issueId)
            ? ` <span class="ui-chip ui-chip--accent calendar-today-tag">Hôm nay</span>`
            : "";
          head = `<h3 class="calendar-date" id="calendar-${escapeHtml(ev.date)}">${escapeHtml(ev.date)}${today}</h3>`;
        }
        const tz = ev.timezone || "giờ VN";
        const time = ev.time
          ? `<span class="calendar-time">${escapeHtml(ev.time)} (${escapeHtml(tz)})</span>`
          : "";
        const topic = ev.topic
          ? `<span class="calendar-topic">${escapeHtml(ev.topic)}</span>`
          : "";
        return `${head}<article class="calendar-item">
          ${time ? `<div>${time}</div>` : ""}
          <strong class="calendar-item-title">${escapeHtml(ev.title || "")}</strong>
          ${topic ? `<div>${topic}</div>` : ""}
          ${ev.note ? `<p class="calendar-note">${escapeHtml(ev.note)}</p>` : ""}
          ${sourcesHtml(ev.sources)}
        </article>`;
      })
      .join("");
  }

  function renderCalendarPanelMarkup(events, issueId) {
    return `<div class="calendar-panel" id="calendar-panel-full" hidden>
        <div class="calendar-panel-head">
          <h2 id="calendar-dialog-title">Lịch sự kiện</h2>
          <button type="button" class="calendar-panel-close icon-btn" aria-label="Đóng lịch">
            <svg class="toolbar-icon" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m7 7 10 10M17 7 7 17" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>
          </button>
        </div>
        <p class="calendar-hint">Trong 14 ngày tới (tính từ ngày số báo)</p>
        <div class="calendar-panel-body">${renderCalendarEventList(events, issueId)}</div>
      </div>`;
  }

  /** Mobile: panel host only (header icon opens modal). */
  function renderCalendarMobileHost(events, issueId) {
    if (!events.length) return "";
    return `<div class="calendar-mobile-host" id="lich-su-kien" hidden aria-hidden="true">${renderCalendarPanelMarkup(events, issueId)}</div>`;
  }

  function renderCalendarStrip(events, issueId) {
    if (!events.length) return "";
    const next = events[0];
    const count = events.length;
    const countLabel = count === 1 ? "1 sự kiện" : `${count} sự kiện`;
    const todayTag = isEventOnIssueDay(next.date, issueId)
      ? `<span class="ui-chip ui-chip--accent calendar-teaser-today">Hôm nay</span>`
      : "";
    const calIcon = `<svg class="calendar-teaser-icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="4" y="5.5" width="16" height="14" rx="1.25" fill="none" stroke="currentColor" stroke-width="1.75"/><path d="M4 9.5h16M8 3.5v4M16 3.5v4" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>`;
    return `<div class="calendar-strip-wrap calendar-teaser" id="lich-su-kien">
      <button type="button" class="calendar-strip-toggle calendar-teaser-bar" aria-expanded="false" aria-controls="calendar-panel-full">
        <span class="calendar-teaser-accent" aria-hidden="true"></span>
        ${calIcon}
        <span class="calendar-teaser-label">Sắp diễn ra</span>
        <span class="ui-chip ui-chip--plain calendar-teaser-badge">${escapeHtml(countLabel)}</span>
        <span class="calendar-teaser-event">
          <span class="ui-chip ui-chip--plain calendar-date-chip">${escapeHtml(formatShortDate(next.date))}</span>
          ${todayTag}
          <span class="calendar-teaser-title">${escapeHtml(truncateText(next.title, 64))}</span>
        </span>
        <span class="ui-chip ui-chip--action calendar-teaser-action">Xem lịch <span class="calendar-teaser-caret" aria-hidden="true">▾</span></span>
      </button>
      ${renderCalendarPanelMarkup(events, issueId)}
    </div>`;
  }

  function useCalendarModal() {
    return isMobileLayout();
  }

  function getCalendarPanel() {
    const hosted = document.querySelector("#lich-su-kien #calendar-panel-full");
    if (hosted) return hosted;
    return document.querySelector("body > #calendar-panel-full");
  }

  function cleanupCalendarDomBeforeRender() {
    document.querySelectorAll("body > #calendar-panel-full").forEach((el) => {
      el.remove();
    });
    document.body.classList.remove("calendar-sheet-open");
    const backdrop = document.querySelector(".calendar-backdrop");
    if (backdrop) backdrop.hidden = true;
  }

  function ensureCalendarInteractionHandlers() {
    const doc = document.documentElement;
    if (!doc.dataset.calendarClickBound) {
      doc.dataset.calendarClickBound = "1";
      document.addEventListener("click", (e) => {
        const paper = document.getElementById("paper-root");
        if (!paper) return;
        const wrap = paper.querySelector("#lich-su-kien");
        if (!wrap) return;

        const panel = getCalendarPanel();
        const closeBtn = e.target.closest(".calendar-panel-close");
        if (closeBtn && panel?.contains(closeBtn)) {
          e.preventDefault();
          setCalendarOpen(false, paper);
          return;
        }

        const toggle = e.target.closest(".calendar-strip-toggle");
        if (toggle && wrap.contains(toggle)) {
          e.preventDefault();
          setCalendarOpen(!!panel?.hidden, paper);
        }
      });
    }

    if (!doc.dataset.calendarBackdropBound) {
      let backdrop = document.querySelector(".calendar-backdrop");
      if (!backdrop) {
        backdrop = document.createElement("div");
        backdrop.className = "calendar-backdrop";
        backdrop.hidden = true;
        document.body.appendChild(backdrop);
      }
      doc.dataset.calendarBackdropBound = "1";
      backdrop.addEventListener("click", () => {
        const paper = document.getElementById("paper-root");
        if (paper) setCalendarOpen(false, paper);
      });
    }
  }

  function calendarPanelHost(root) {
    return (
      root?.querySelector(".calendar-strip-wrap") ||
      root?.querySelector(".calendar-mobile-host") ||
      root?.querySelector("#lich-su-kien") ||
      null
    );
  }

  function syncCalendarPanelMount(open, root) {
    const panel = getCalendarPanel();
    const host = calendarPanelHost(root);
    if (!panel || !host) return;
    if (open && useCalendarModal()) {
      if (panel.parentElement !== document.body) document.body.appendChild(panel);
    } else if (panel.parentElement === document.body) {
      host.appendChild(panel);
    }
  }

  function setCalendarOpen(open, root) {
    const panel = getCalendarPanel();
    const toggle = root?.querySelector(".calendar-strip-toggle");
    const backdrop = document.querySelector(".calendar-backdrop");
    if (!panel || !root) return;
    const modal = open && useCalendarModal();
    if (open) syncCalendarPanelMount(true, root);
    panel.hidden = !open;
    toggle?.setAttribute("aria-expanded", open ? "true" : "false");
    panel.classList.toggle("calendar-panel--open", modal);
    document.body.classList.toggle("calendar-sheet-open", modal);
    if (backdrop) backdrop.hidden = !modal;
    if (modal) {
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "true");
      panel.setAttribute("aria-labelledby", "calendar-dialog-title");
    } else {
      panel.removeAttribute("role");
      panel.removeAttribute("aria-modal");
      panel.removeAttribute("aria-labelledby");
    }
    if (!open) {
      panel.classList.remove("calendar-panel--open");
      document.body.classList.remove("calendar-sheet-open");
      if (backdrop) backdrop.hidden = true;
      syncCalendarPanelMount(false, root);
    }
    try {
      if (useCalendarModal()) {
        localStorage.setItem(CALENDAR_OPEN_KEY, "0");
      } else {
        localStorage.setItem(CALENDAR_OPEN_KEY, open ? "1" : "0");
      }
    } catch {
      /* ignore */
    }
  }

  function bindCalendarChrome(root) {
    ensureCalendarInteractionHandlers();
    const wrap = root.querySelector("#lich-su-kien");
    if (!wrap) {
      document.body.classList.remove("calendar-sheet-open");
      document.querySelector(".calendar-backdrop")?.setAttribute("hidden", "");
      return;
    }

    let initiallyOpen = false;
    if (useCalendarModal()) {
      try {
        localStorage.setItem(CALENDAR_OPEN_KEY, "0");
      } catch {
        /* ignore */
      }
    } else {
      try {
        initiallyOpen = localStorage.getItem(CALENDAR_OPEN_KEY) === "1";
      } catch {
        initiallyOpen = false;
      }
    }
    setCalendarOpen(initiallyOpen, root);

    if (!document.documentElement.dataset.calendarEscBound) {
      document.documentElement.dataset.calendarEscBound = "1";
      document.addEventListener(
        "keydown",
        (e) => {
          if (e.key !== "Escape") return;
          const panel = getCalendarPanel();
          const paper = document.getElementById("paper-root");
          if (panel && !panel.hidden && paper) {
            e.preventDefault();
            e.stopImmediatePropagation();
            setCalendarOpen(false, paper);
          }
        },
        true
      );
    }
  }

  function renderArticles(sec, issueId) {
    return (sec.items || [])
      .map((it, idx) => {
        const artId = articleDomId(issueId, sec, idx);
        return `<article class="article" id="${escapeHtml(artId)}">
          <h3>${escapeHtml(it.headline)}</h3>
          ${it.meta ? `<div class="meta">${escapeHtml(it.meta)}</div>` : ""}
          ${bodyHtml(it.body)}
          ${sourcesHtml(it.sources)}
        </article>`;
      })
      .join("");
  }

  function tocAnchorLink(id, labelHtml) {
    return `<a class="toc-link" href="#${escapeHtml(id)}">${labelHtml}</a>`;
  }

  function tocEntries(sections, extras = {}) {
    const rows = [];
    if (extras.followupCount) {
      rows.push(
        `<li><span>${tocAnchorLink("theo-doi-tin-cu", "<strong>Theo dõi tin cũ</strong>")} — ${extras.followupCount} tin</span></li>`
      );
    }
    if (extras.calendarCount) {
      rows.push(
        `<li><span>${tocAnchorLink("lich-su-kien", "<strong>Lịch sự kiện</strong>")} — ${extras.calendarCount} sự kiện</span></li>`
      );
    }
    let i = 0;
    while (i < sections.length) {
      const sec = sections[i];
      if (sec.topic) {
        const topic = sec.topic;
        const topicId = topicSlug(topic);
        const parts = [];
        while (i < sections.length && sections[i].topic === topic) {
          const s = sections[i];
          const n = (s.items || []).length;
          if (s.subtitle) {
            const subId = subsectionSlug(topic, s.subtitle);
            parts.push(
              tocAnchorLink(
                subId,
                `${escapeHtml(s.subtitle)} ${n}`
              )
            );
          } else parts.push(`${n} tin`);
          i += 1;
        }
        rows.push(
          `<li><span>${tocAnchorLink(topicId, `<strong>${escapeHtml(topic)}</strong>`)} — ${parts.join(" · ")}</span></li>`
        );
      } else {
        const id = sectionSlug(sec.title);
        const count = (sec.items || []).length;
        rows.push(
          `<li><span>${tocAnchorLink(id, `<strong>${escapeHtml(sec.title)}</strong>`)} — ${count} tin</span></li>`
        );
        i += 1;
      }
    }
    return rows.join("");
  }

  function renderSubsectionBlock(sec, issueId) {
    const subId = sec.subtitle
      ? subsectionSlug(sec.topic, sec.subtitle)
      : "";
    const subhead = sec.subtitle
      ? `<h3 class="subsection-title" id="${escapeHtml(subId)}">${escapeHtml(sec.subtitle)}</h3>`
      : "";
    const intro = sec.intro
      ? `<div class="intro">${escapeHtml(sec.intro)}</div>`
      : "";
    return `<div class="subsection-block">${subhead}${intro}<div class="articles-columns">${renderArticles(sec, issueId)}</div></div>`;
  }

  function renderSectionBlocks(sections, issueId) {
    const blocks = [];
    let i = 0;
    while (i < sections.length) {
      const sec = sections[i];
      if (sec.topic) {
        const topic = sec.topic;
        const subs = [];
        while (i < sections.length && sections[i].topic === topic) {
          subs.push(sections[i]);
          i += 1;
        }
        const id = topicSlug(topic);
        blocks.push(
          `<section class="section-block topic-group">
        <h2 id="${escapeHtml(id)}">${escapeHtml(topic)}</h2>
        ${subs.map((s) => renderSubsectionBlock(s, issueId)).join("")}
        <p class="back-to-toc"><a class="toc-link" href="#muc-luc">↑ Mục lục</a></p>
      </section>`
        );
      } else {
        const id = sectionSlug(sec.title);
        blocks.push(
          `<section class="section-block">
        <h2 id="${escapeHtml(id)}">${escapeHtml(sec.title)}</h2>
        ${sec.intro ? `<div class="intro">${escapeHtml(sec.intro)}</div>` : ""}
        <div class="articles-columns">${renderArticles(sec, issueId)}</div>
        <p class="back-to-toc"><a class="toc-link" href="#muc-luc">↑ Mục lục</a></p>
      </section>`
        );
        i += 1;
      }
    }
    return blocks.join("");
  }

  function renderIssue(data, tag, issueId) {
    const sections = filterSections(data, tag);
    const dateIso = data.date;
    const showHighlights = tag === "all";
    const showExtras = tag === "all";
    const followups = showExtras ? data.followups || [] : [];
    const calendarEvents = showExtras
      ? upcomingCalendarEvents(data, issueId)
      : [];

    let toc = "";
    if (
      sections.length ||
      (showExtras && (followups.length || calendarEvents.length))
    ) {
      toc = `<div class="toc-block" id="muc-luc">
        <div class="toc-block-head">
          <h2>Trong số này</h2>
        </div>
        <ul>${tocEntries(sections, {
          followupCount: followups.length,
          calendarCount: calendarEvents.length,
        })}</ul>
      </div>`;
    }

    let empty = "";
    if (tag !== "all" && !sections.length) {
      empty = `<div class="empty-tag">${escapeHtml(
        EMPTY_TAG_COPY[tag] ||
          "Không có tin nào khớp bộ lọc này trong số báo đã chọn."
      )}</div>`;
    }

    const sectionHtml = renderSectionBlocks(sections, issueId);
    const followupsHtml = followups.length ? renderFollowups(followups) : "";
    const calendarStripHtml =
      showExtras && calendarEvents.length
        ? isMobileLayout()
          ? renderCalendarMobileHost(calendarEvents, issueId)
          : renderCalendarStrip(calendarEvents, issueId)
        : "";

    const highlights = showHighlights
      ? `<div class="highlights"><h2>Điểm nhanh</h2><ol>${(data.highlights || [])
          .map((h) => `<li>${escapeHtml(h)}</li>`)
          .join("")}</ol></div>`
      : "";

    return `
      <header class="masthead">
        <h1>${escapeHtml(MASTHEAD)}</h1>
        <div class="date-line">${escapeHtml(data.date_vn || vnDate(dateIso))}</div>
        ${data.tagline ? `<div class="tagline">${escapeHtml(data.tagline)}</div>` : ""}
      </header>
      ${calendarStripHtml}
      ${highlights}
      ${toc}
      ${followupsHtml}
      ${empty}
      ${sectionHtml}
      ${data.footer_note ? `<div class="footer-note">${escapeHtml(data.footer_note)}</div>` : ""}
    `;
  }

  function renderTags(activeTag, onSelect) {
    const strip = document.getElementById("tag-strip");
    if (!strip) return;
    strip.innerHTML = `<p class="tag-strip-label">Lọc theo mục</p><div class="tag-chips-scroll"><div class="tag-chips" role="group" aria-label="Lọc mục"></div></div>`;
    const chips = strip.querySelector(".tag-chips");
    tagsForLayout().forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = t.label;
      btn.className = t.id === activeTag ? "active" : "";
      btn.dataset.tagId = t.id;
      btn.setAttribute("aria-pressed", t.id === activeTag ? "true" : "false");
      btn.addEventListener("click", () => onSelect(t.id));
      chips.appendChild(btn);
    });
  }

  async function loadIndex() {
    const res = await fetchJson(asset("issues/index.json"));
    if (!res.ok) throw new Error("Không tải được danh sách số báo");
    return res.json();
  }

  async function loadIssue(date) {
    const res = await fetch(asset(`issues/${date}/content.json`));
    if (!res.ok) throw new Error("Không tải được số báo " + date);
    return res.json();
  }

  function updateFavButton(date) {
    const btn = document.getElementById("btn-fav");
    if (!btn) return;
    const on = getFavorites().includes(date);
    btn.textContent = on ? "★ Đã lưu" : "☆ Lưu số báo";
    btn.classList.toggle("fav-on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function setupPdfPanel(date) {
    const panel = document.getElementById("pdf-panel");
    const toggle = document.getElementById("btn-pdf");
    const close = document.getElementById("btn-pdf-close");
    const iframe = document.getElementById("pdf-frame");
    const dl = document.getElementById("pdf-download");
    if (!panel || !toggle) return;

    const pdfUrl = asset(`issues/${date}/paper.pdf`);
    if (iframe) iframe.src = pdfUrl;
    if (dl) {
      dl.href = pdfUrl;
      dl.download = `daily-news-${date}.pdf`;
    }

    toggle.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
    });
    close?.addEventListener("click", () => {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    });
  }

  async function initReader() {
    const root = document.getElementById("paper-root");
    const status = document.getElementById("status");
    if (!root) return;

    ensureCalendarInteractionHandlers();
    initThemeToggle();
    initMobileChrome();
    let { date, tag, anchor: pendingAnchor, searchQuery } = parseParams();

    try {
      const index = await loadIndex();
      initSearch(index);
      if (!date) date = index.latest;
      const data = await loadIssue(date);
      data.masthead = MASTHEAD;

      document.title = `${MASTHEAD} — ${data.date_vn || vnDate(data.date)}`;

      const prev = index.issues
        .map((i) => i.date)
        .sort()
        .filter((d) => d < date)
        .pop();
      const next = index.issues
        .map((i) => i.date)
        .sort()
        .filter((d) => d > date)
        .shift();

      const render = (newTag, options = {}) => {
        tag = newTag;
        const urlAnchor = options.anchor ?? options.scrollTo ?? "";
        const q = options.keepSearch ? searchQuery : parseParams().searchQuery;
        syncUrl(date, tag, urlAnchor, q);
        cleanupCalendarDomBeforeRender();
        root.innerHTML = renderIssue(data, tag, date);
        bindCalendarChrome(root);
        renderTags(tag, render);
        injectIssuePager(root, prev, next);
        if (options.scrollTo) {
          requestAnimationFrame(() => {
            if (options.scrollTo === "lich-su-kien") {
              openCalendarFromToc(root);
            } else {
              scrollToAnchor(options.scrollTo);
            }
          });
        }
      };

      root.addEventListener("click", (e) => {
        const a = e.target.closest("a.toc-link");
        if (!a || !root.contains(a)) return;
        const href = a.getAttribute("href");
        if (!href || !href.startsWith("#")) return;
        const id = decodeURIComponent(href.slice(1));
        if (!id || id === "muc-luc") return;
        e.preventDefault();
        if (tag !== "all") {
          render("all", { scrollTo: id, anchor: id });
        } else if (id === "lich-su-kien") {
          syncUrl(date, tag, id, parseParams().searchQuery);
          openCalendarFromToc(root);
        } else {
          syncUrl(date, tag, id, parseParams().searchQuery);
          scrollToAnchor(id);
        }
      });

      window.addEventListener("hashchange", () => {
        const { anchor } = parseParams();
        if (!anchor) return;
        const paper = document.getElementById("paper-root");
        if (anchor === "lich-su-kien") openCalendarFromToc(paper);
        else scrollToAnchor(anchor);
      });

      if (pendingAnchor) {
        render("all", { scrollTo: pendingAnchor, anchor: pendingAnchor });
      } else {
        render(tag);
      }
      updateFavButton(date);
      setupPdfPanel(date);

      document.getElementById("btn-fav")?.addEventListener("click", () => {
        toggleFavorite(date);
        updateFavButton(date);
      });

      const prevA = document.getElementById("nav-prev");
      const nextA = document.getElementById("nav-next");
      if (prevA) {
        if (prev) {
          prevA.href = asset(`index.html?date=${prev}`);
          prevA.hidden = false;
        } else prevA.hidden = true;
      }
      if (nextA) {
        if (next) {
          nextA.href = asset(`index.html?date=${next}`);
          nextA.hidden = false;
        } else nextA.hidden = true;
      }

      status?.remove();
    } catch (e) {
      if (status) {
        status.className = "error-msg";
        status.textContent = e.message || String(e);
      }
    }
  }

  const ARCHIVE_TYPE_CHIEU = "chieu";
  const ARCHIVE_TYPE_SANG = "sang";

  function parseArchiveTypeParam() {
    const t = new URLSearchParams(location.search).get("type");
    if (t === ARCHIVE_TYPE_SANG || t === ARCHIVE_TYPE_CHIEU) {
      return t;
    }
    return null;
  }

  function parseArchivePageParam() {
    const raw = parseInt(new URLSearchParams(location.search).get("page") || "1", 10);
    return Number.isFinite(raw) && raw >= 1 ? raw : 1;
  }

  function archiveQueryParams(page, type) {
    const q = new URLSearchParams();
    const archiveType = type !== undefined ? type : parseArchiveTypeParam();
    if (archiveType) q.set("type", archiveType);
    if (page > 1) q.set("page", String(page));
    return q;
  }

  function archivePageHref(page, type) {
    const qs = archiveQueryParams(page, type).toString();
    return location.pathname + (qs ? "?" + qs : "");
  }

  function archiveIssueMeta(index) {
    const map = new Map();
    for (const row of index.issues) {
      map.set(row.date, row);
    }
    return map;
  }

  function archiveEditionOf(issueId, meta) {
    const row = meta.get(issueId);
    if (row && row.edition === ARCHIVE_TYPE_CHIEU) return ARCHIVE_TYPE_CHIEU;
    if (issueId.endsWith(CHIEU_SUFFIX)) return ARCHIVE_TYPE_CHIEU;
    return ARCHIVE_TYPE_SANG;
  }

  function filterArchiveIssueIds(index, type, meta) {
    const ids = index.issues.map((i) => i.date);
    if (!type) return ids.sort().reverse();
    const filtered = ids.filter((id) => {
      if (type === ARCHIVE_TYPE_CHIEU) {
        return archiveEditionOf(id, meta) === ARCHIVE_TYPE_CHIEU;
      }
      if (type === ARCHIVE_TYPE_SANG) {
        return archiveEditionOf(id, meta) === ARCHIVE_TYPE_SANG;
      }
      return true;
    });
    return filtered.sort().reverse();
  }

  function archiveRowBadges(issueId, index, meta, currentPage) {
    const parts = [];
    if (issueId === index.latest && currentPage === 1) {
      parts.push('<span class="badge">Mới nhất</span>');
    }
    const edition = archiveEditionOf(issueId, meta);
    parts.push(
      `<span class="badge badge-edition">${edition === ARCHIVE_TYPE_CHIEU ? "Chiều" : "Sáng"}</span>`
    );
    if (!parts.length) return "";
    return `<span class="archive-row-badges">${parts.join("")}</span>`;
  }

  function archivePageNumbers(current, total) {
    if (total <= 7) {
      return Array.from({ length: total }, (_, i) => i + 1);
    }
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

  function renderArchivePaginationNav(currentPage, totalPages) {
    let nav = document.getElementById("archive-pagination");
    if (!nav) {
      nav = document.createElement("nav");
      nav.id = "archive-pagination";
      nav.className = "archive-pagination";
      nav.setAttribute("aria-label", "Phân trang kho số cũ");
    }
    if (totalPages <= 1) {
      nav.hidden = true;
      nav.innerHTML = "";
      return nav;
    }
    nav.hidden = false;
    const prevDisabled = currentPage <= 1;
    const nextDisabled = currentPage >= totalPages;
    const nums = archivePageNumbers(currentPage, totalPages)
      .map((p) => {
        if (p === null) {
          return `<span class="archive-page-ellipsis" aria-hidden="true">…</span>`;
        }
        if (p === currentPage) {
          return `<span class="archive-page-current" aria-current="page">${p}</span>`;
        }
        return `<a class="archive-page-link" href="${escapeHtml(archivePageHref(p))}" data-archive-page="${p}">${p}</a>`;
      })
      .join("");
    nav.innerHTML = `
      <a class="archive-page-nav${prevDisabled ? " is-disabled" : ""}" href="${prevDisabled ? "#" : escapeHtml(archivePageHref(currentPage - 1))}" data-archive-page="${currentPage - 1}" aria-label="Trang trước"${prevDisabled ? ' aria-disabled="true" tabindex="-1"' : ""}>← Trước</a>
      <div class="archive-page-nums" role="group" aria-label="Số trang">${nums}</div>
      <a class="archive-page-nav${nextDisabled ? " is-disabled" : ""}" href="${nextDisabled ? "#" : escapeHtml(archivePageHref(currentPage + 1))}" data-archive-page="${currentPage + 1}" aria-label="Trang sau"${nextDisabled ? ' aria-disabled="true" tabindex="-1"' : ""}>Sau →</a>`;
    return nav;
  }

  function renderArchiveTypeFilters(activeType, onSelect) {
    const wrap = document.getElementById("archive-filters");
    if (!wrap) return;
    const chips = [
      { id: null, label: "Tất cả" },
      { id: ARCHIVE_TYPE_SANG, label: "Buổi sáng" },
      { id: ARCHIVE_TYPE_CHIEU, label: "Buổi chiều" },
    ];
    wrap.innerHTML = `<div class="tag-chips-scroll"><div class="tag-chips archive-type-chips" role="list">${chips
      .map(
        ({ id, label }) =>
          `<button type="button" role="listitem" class="${activeType === id ? "active" : ""}" data-archive-type="${id ?? ""}" aria-pressed="${activeType === id ? "true" : "false"}">${escapeHtml(label)}</button>`
      )
      .join("")}</div></div>`;
    wrap.querySelectorAll("[data-archive-type]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const raw = btn.getAttribute("data-archive-type");
        onSelect(raw === "" ? null : raw);
      });
    });
  }

  async function initArchive() {
    const listEl = document.getElementById("archive-list");
    const emptyEl = document.getElementById("archive-empty");
    const favEl = document.getElementById("favorites-list");
    if (!listEl) return;

    initThemeToggle();
    initMobileChrome();
    const index = await loadIndex();
    initSearch(index);
    const meta = archiveIssueMeta(index);

    function datesForType(type) {
      return filterArchiveIssueIds(index, type, meta);
    }

    function bindArchiveFavButtons() {
      listEl.querySelectorAll(".archive-fav").forEach((btn) => {
        const d = btn.dataset.date;
        const refresh = () => {
          btn.textContent = getFavorites().includes(d) ? "★" : "☆";
          btn.classList.toggle("fav-on", getFavorites().includes(d));
        };
        refresh();
        btn.addEventListener("click", () => {
          toggleFavorite(d);
          refresh();
          renderFavorites();
        });
      });
    }

    function renderArchiveListPage(page, typeOverride) {
      const archiveType =
        typeOverride !== undefined ? typeOverride : parseArchiveTypeParam();
      const dates = datesForType(archiveType);
      const totalPages = Math.max(1, Math.ceil(dates.length / ARCHIVE_PAGE_SIZE));
      const currentPage = Math.min(Math.max(1, page), totalPages);
      if (currentPage !== page) {
        history.replaceState(null, "", archivePageHref(currentPage, archiveType));
      }

      renderArchiveTypeFilters(archiveType, (nextType) => {
        history.pushState(null, "", archivePageHref(1, nextType));
        renderArchiveListPage(1, nextType);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });

      if (emptyEl) {
        emptyEl.hidden = true;
        emptyEl.textContent = "";
      }

      const start = (currentPage - 1) * ARCHIVE_PAGE_SIZE;
      const slice = dates.slice(start, start + ARCHIVE_PAGE_SIZE);
      listEl.innerHTML = slice
        .map(
          (d) =>
            `<li>${archiveRowBadges(d, index, meta, currentPage)}<a class="issue-link" href="${asset(`index.html?date=${d}`)}">${escapeHtml(issueListLabel(d, index))}</a>
          <button type="button" class="archive-fav" data-date="${d}" aria-label="Lưu số báo">☆</button></li>`
        )
        .join("");
      bindArchiveFavButtons();

      const nav = renderArchivePaginationNav(currentPage, totalPages);
      const existingNav = document.getElementById("archive-pagination");
      if (existingNav) existingNav.replaceWith(nav);
      else listEl.insertAdjacentElement("afterend", nav);
    }

    if (!document.body.dataset.archivePaginationBound) {
      document.body.dataset.archivePaginationBound = "1";
      document.body.addEventListener("click", (e) => {
        const link = e.target.closest("#archive-pagination [data-archive-page]");
        if (!link || link.classList.contains("is-disabled")) return;
        e.preventDefault();
        const page = parseInt(link.dataset.archivePage, 10);
        if (!Number.isFinite(page) || page < 1) return;
        history.pushState(null, "", archivePageHref(page));
        renderArchiveListPage(page);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      window.addEventListener("popstate", () => {
        renderArchiveListPage(parseArchivePageParam());
      });
    }

    renderArchiveListPage(parseArchivePageParam());

    function renderFavorites() {
      if (!favEl) return;
      const fav = getFavorites();
      if (!fav.length) {
        favEl.innerHTML =
          '<p class="favorites-empty">Chưa có số báo đã lưu. Bấm ☆ trên trang đọc hoặc trong danh sách bên trên.</p>';
        return;
      }
      favEl.innerHTML = `<ul class="archive-list">${fav
        .map(
          (d) =>
            `<li><a class="issue-link" href="${asset(`index.html?date=${d}`)}">${escapeHtml(issueListLabel(d, index))}</a></li>`
        )
        .join("")}</ul>`;
    }
    renderFavorites();
  }

  window.DailyNews = {
    asset,
    getFavorites,
    vnDate,
    MASTHEAD,
    slugify,
    topicSlug,
    sectionSlug,
    subsectionSlug,
    articleDomId,
    normSearch,
    removeDiacritics,
  };

  if (document.body.dataset.page === "reader") initReader();
  if (document.body.dataset.page === "archive") initArchive();
})();
