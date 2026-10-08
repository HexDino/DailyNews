(function () {
  "use strict";

  const MASTHEAD = "Daily News";
  const FAV_KEY = "dailynews-favorites";
  const READ_KEY = "dailynews-read";
  const THEME_KEY = "dailynews-theme";
  /** @type {Map<string, object>|null} */
  let issueContentCache = null;
  /** @type {object[]|null} */
  let searchCorpus = null;
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

  function asset(path) {
    const p = path.replace(/^\//, "");
    return basePath + p;
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

  function getReadMap() {
    try {
      return JSON.parse(localStorage.getItem(READ_KEY) || "{}");
    } catch {
      return {};
    }
  }

  function readStorageKey(issueId, articleId) {
    return `${issueId}|${articleId}`;
  }

  function isArticleRead(issueId, articleId) {
    return !!getReadMap()[readStorageKey(issueId, articleId)];
  }

  function setArticleRead(issueId, articleId, read) {
    const map = getReadMap();
    const k = readStorageKey(issueId, articleId);
    if (read) map[k] = 1;
    else delete map[k];
    localStorage.setItem(READ_KEY, JSON.stringify(map));
  }

  function clearReadForIssue(issueId) {
    const map = getReadMap();
    const prefix = `${issueId}|`;
    Object.keys(map).forEach((k) => {
      if (k.startsWith(prefix)) delete map[k];
    });
    localStorage.setItem(READ_KEY, JSON.stringify(map));
  }

  function countReadProgress(issueId, data) {
    let total = 0;
    let read = 0;
    (data.sections || []).forEach((sec) => {
      (sec.items || []).forEach((it, idx) => {
        total += 1;
        const id = articleDomId(issueId, sec, idx);
        if (isArticleRead(issueId, id)) read += 1;
      });
    });
    return { read, total };
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
    btn.textContent = dark ? "☾ Tối" : "☀ Sáng";
    btn.setAttribute(
      "aria-label",
      dark ? "Đang dùng giao diện tối, chuyển sang sáng" : "Đang dùng giao diện sáng, chuyển sang tối"
    );
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

  function snippetForItem(item, terms) {
    const source =
      (item.body && item.body[0]) || item.headline || item.meta || "";
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
        const nPart = normSearch(part);
        const hit = terms.some(
          (t) => nPart.includes(t) || t.includes(nPart) || part.length > 2 && t.includes(nPart)
        );
        if (hit) return `<mark>${escapeHtml(part)}</mark>`;
        return escapeHtml(part);
      })
      .join("");
  }

  async function ensureAllIssuesCached(index) {
    if (issueContentCache && searchCorpus) {
      return { cache: issueContentCache, corpus: searchCorpus, index };
    }
    issueContentCache = new Map();
    searchCorpus = [];
    await Promise.all(
      index.issues.map(async (entry) => {
        const data = await loadIssue(entry.date);
        issueContentCache.set(entry.date, data);
        (data.sections || []).forEach((sec) => {
          (sec.items || []).forEach((item, idx) => {
            const articleId = articleDomId(entry.date, sec, idx);
            searchCorpus.push({
              issueId: entry.date,
              articleId,
              section: sectionLabel(sec),
              headline: item.headline,
              text: itemSearchText(item, sec),
              item,
            });
          });
        });
      })
    );
    return { cache: issueContentCache, corpus: searchCorpus, index };
  }

  function runSearch(query, corpus) {
    const trimmed = query.trim();
    if (!trimmed) return [];
    const terms = normSearch(trimmed).split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    return corpus.filter((row) => {
      const hay = normSearch(row.text);
      return terms.every((t) => hay.includes(t));
    });
  }

  function issueHref(issueId, articleId) {
    return `${asset(`index.html?date=${encodeURIComponent(issueId)}`)}#${encodeURIComponent(articleId)}`;
  }

  function initSearch(indexRef) {
    const form = document.getElementById("search-form");
    const input = document.getElementById("search-input");
    const panel = document.getElementById("search-panel");
    const statusEl = document.getElementById("search-status");
    const listEl = document.getElementById("search-results");
    const closeBtn = document.getElementById("search-close");
    if (!form || !input || !panel || !listEl) return;

    let indexPromise = indexRef
      ? Promise.resolve(indexRef)
      : loadIndex();

    async function showResults(query, pushUrl) {
      const q = query.trim();
      input.value = q;
      if (!q) {
        panel.hidden = true;
        if (pushUrl) {
          const { date, tag, anchor } = parseParams();
          syncUrl(date, tag, anchor, "");
        }
        return;
      }
      panel.hidden = false;
      statusEl.textContent = "Đang tìm…";
      listEl.innerHTML = "";
      const index = await indexPromise;
      const { corpus } = await ensureAllIssuesCached(index);
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
        .map((row) => {
          const label = issueListLabel(row.issueId, index);
          return `<li class="search-hit">
            <a class="search-hit-link" href="${issueHref(row.issueId, row.articleId)}">
              <span class="search-hit-meta">${escapeHtml(label)} · ${escapeHtml(row.section)}</span>
              <span class="search-hit-headline">${highlightTerms(row.headline, terms)}</span>
              <span class="search-hit-snippet">${snippetForItem(row.item, terms)}</span>
            </a>
          </li>`;
        })
        .join("");
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      showResults(input.value, true);
    });

    closeBtn?.addEventListener("click", () => {
      panel.hidden = true;
      const { date, tag, anchor } = parseParams();
      syncUrl(date, tag, anchor, "");
      input.value = "";
    });

    const { searchQuery } = parseParams();
    if (searchQuery) {
      showResults(searchQuery, false);
    }
  }

  function scrollToAnchor(id) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
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

  function sourcesHtml(sources) {
    if (!sources || !sources.length) return "";
    const parts = sources.map((src) => {
      const name = escapeHtml(src.name || "");
      if (src.url) {
        return `${name} — <a class="source-link" href="${escapeHtml(src.url)}" rel="noopener noreferrer" target="_blank">${escapeHtml(src.url)}</a>`;
      }
      return name;
    });
    return `<div class="sources"><strong>Nguồn:</strong> ${parts.join("; ")}</div>`;
  }

  function renderArticles(sec, issueId) {
    return (sec.items || [])
      .map((it, idx) => {
        const artId = articleDomId(issueId, sec, idx);
        const read = isArticleRead(issueId, artId);
        return `<article class="article${read ? " is-read" : ""}" id="${escapeHtml(artId)}" data-article-id="${escapeHtml(artId)}">
          <div class="article-head">
            <h3>${escapeHtml(it.headline)}</h3>
            <button type="button" class="read-toggle${read ? " is-read" : ""}" data-article-id="${escapeHtml(artId)}" aria-pressed="${read ? "true" : "false"}">${read ? "Đã đọc" : "Đánh dấu đã đọc"}</button>
          </div>
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

  function tocEntries(sections) {
    const rows = [];
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
    const progress = countReadProgress(issueId, data);

    let toc = "";
    if (sections.length) {
      const progressHtml =
        progress.total > 0
          ? `<span class="read-progress" id="read-progress">${progress.read}/${progress.total} đã đọc</span>`
          : "";
      const clearBtn =
        progress.read > 0
          ? `<button type="button" class="read-clear-all" id="read-clear-all">Bỏ đánh dấu tất cả</button>`
          : "";
      toc = `<div class="toc-block" id="muc-luc">
        <div class="toc-block-head">
          <h2>Trong số này</h2>
          ${progressHtml}
        </div>
        <ul>${tocEntries(sections)}</ul>
        ${clearBtn}
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
      ${highlights}
      ${toc}
      ${empty}
      ${sectionHtml}
      ${data.footer_note ? `<div class="footer-note">${escapeHtml(data.footer_note)}</div>` : ""}
    `;
  }

  function renderTags(activeTag, onSelect) {
    const strip = document.getElementById("tag-strip");
    if (!strip) return;
    strip.innerHTML = `<p>Lọc theo mục</p><div class="tag-chips" role="group" aria-label="Lọc mục"></div>`;
    const chips = strip.querySelector(".tag-chips");
    TAGS.forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = t.label;
      btn.className = t.id === activeTag ? "active" : "";
      btn.setAttribute("aria-pressed", t.id === activeTag ? "true" : "false");
      btn.addEventListener("click", () => onSelect(t.id));
      chips.appendChild(btn);
    });
  }

  async function loadIndex() {
    const res = await fetch(asset("issues/index.json"));
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

  function bindReadControls(root, issueId, onRerender) {
    root.querySelectorAll(".read-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const artId = btn.dataset.articleId;
        if (!artId) return;
        const next = !isArticleRead(issueId, artId);
        setArticleRead(issueId, artId, next);
        onRerender();
      });
    });
    root.querySelector("#read-clear-all")?.addEventListener("click", () => {
      clearReadForIssue(issueId);
      onRerender();
    });
  }

  async function initReader() {
    const root = document.getElementById("paper-root");
    const status = document.getElementById("status");
    if (!root) return;

    initThemeToggle();
    let { date, tag, anchor: pendingAnchor, searchQuery } = parseParams();

    try {
      const index = await loadIndex();
      initSearch(index);
      if (!date) date = index.latest;
      const data = await loadIssue(date);
      data.masthead = MASTHEAD;

      document.title = `${MASTHEAD} — ${data.date_vn || vnDate(data.date)}`;

      const render = (newTag, options = {}) => {
        tag = newTag;
        const urlAnchor = options.anchor ?? options.scrollTo ?? "";
        const q = options.keepSearch ? searchQuery : parseParams().searchQuery;
        syncUrl(date, tag, urlAnchor, q);
        root.innerHTML = renderIssue(data, tag, date);
        renderTags(tag, render);
        bindReadControls(root, date, () => render(tag, { keepSearch: true }));
        if (options.scrollTo) {
          requestAnimationFrame(() => scrollToAnchor(options.scrollTo));
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
        } else {
          syncUrl(date, tag, id, parseParams().searchQuery);
          scrollToAnchor(id);
        }
      });

      window.addEventListener("hashchange", () => {
        const { anchor } = parseParams();
        if (anchor) scrollToAnchor(anchor);
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

  async function initArchive() {
    const listEl = document.getElementById("archive-list");
    const favEl = document.getElementById("favorites-list");
    if (!listEl) return;

    initThemeToggle();
    const index = await loadIndex();
    initSearch(index);
    const { cache } = await ensureAllIssuesCached(index);
    const dates = index.issues.map((i) => i.date).sort().reverse();

    listEl.innerHTML = dates
      .map((d) => {
        const latest = d === index.latest ? `<span class="badge">Mới nhất</span>` : "";
        const data = cache.get(d);
        const prog = data ? countReadProgress(d, data) : { read: 0, total: 0 };
        const progHtml =
          prog.total > 0
            ? `<span class="archive-read-progress">${prog.read}/${prog.total} đã đọc</span>`
            : "";
        return `<li>${latest}<a class="issue-link" href="${asset(`index.html?date=${d}`)}">${escapeHtml(issueListLabel(d, index))}</a>
          ${progHtml}
          <button type="button" class="archive-fav" data-date="${d}" aria-label="Lưu số báo">☆</button></li>`;
      })
      .join("");

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
    getReadMap,
    isArticleRead,
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
