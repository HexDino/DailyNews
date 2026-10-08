(function () {
  "use strict";

  const MASTHEAD = "Daily News";
  const FAV_KEY = "dailynews-favorites";
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

  function parseParams() {
    const q = new URLSearchParams(location.search);
    let date = q.get("date");
    let tag = q.get("tag") || "all";
    if (location.hash.startsWith("#tag=")) {
      tag = location.hash.slice(5) || "all";
    }
    return { date, tag };
  }

  function syncUrl(date, tag) {
    const q = new URLSearchParams();
    if (date) q.set("date", date);
    if (tag && tag !== "all") q.set("tag", tag);
    const qs = q.toString();
    const url = location.pathname + (qs ? "?" + qs : "");
    history.replaceState(null, "", url);
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

  function renderArticles(sec) {
    return (sec.items || [])
      .map(
        (it) => `<article class="article">
          <h3>${escapeHtml(it.headline)}</h3>
          ${it.meta ? `<div class="meta">${escapeHtml(it.meta)}</div>` : ""}
          ${bodyHtml(it.body)}
          ${sourcesHtml(it.sources)}
        </article>`
      )
      .join("");
  }

  function tocEntries(sections) {
    const rows = [];
    let i = 0;
    while (i < sections.length) {
      const sec = sections[i];
      if (sec.topic) {
        const topic = sec.topic;
        const parts = [];
        while (i < sections.length && sections[i].topic === topic) {
          const s = sections[i];
          const n = (s.items || []).length;
          if (s.subtitle) parts.push(`${escapeHtml(s.subtitle)} ${n}`);
          else parts.push(`${n} tin`);
          i += 1;
        }
        rows.push(
          `<li><span><strong>${escapeHtml(topic)}</strong> — ${parts.join(" · ")}</span></li>`
        );
      } else {
        rows.push(
          `<li><span><strong>${escapeHtml(sec.title)}</strong> — ${(sec.items || []).length} tin</span></li>`
        );
        i += 1;
      }
    }
    return rows.join("");
  }

  function renderSubsectionBlock(sec) {
    const subhead = sec.subtitle
      ? `<h3 class="subsection-title">${escapeHtml(sec.subtitle)}</h3>`
      : "";
    const intro = sec.intro
      ? `<div class="intro">${escapeHtml(sec.intro)}</div>`
      : "";
    return `<div class="subsection-block">${subhead}${intro}<div class="articles-columns">${renderArticles(sec)}</div></div>`;
  }

  function renderSectionBlocks(sections) {
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
        const id = `topic-${topic.replace(/\s+/g, "-")}`;
        blocks.push(
          `<section class="section-block topic-group" id="${escapeHtml(id)}">
        <h2>${escapeHtml(topic)}</h2>
        ${subs.map(renderSubsectionBlock).join("")}
      </section>`
        );
      } else {
        const id = sec.title.replace(/\s+/g, "-");
        blocks.push(
          `<section class="section-block" id="sec-${escapeHtml(id)}">
        <h2>${escapeHtml(sec.title)}</h2>
        ${sec.intro ? `<div class="intro">${escapeHtml(sec.intro)}</div>` : ""}
        <div class="articles-columns">${renderArticles(sec)}</div>
      </section>`
        );
        i += 1;
      }
    }
    return blocks.join("");
  }

  function renderIssue(data, tag) {
    const sections = filterSections(data, tag);
    const dateIso = data.date;
    const showHighlights = tag === "all";

    let toc = "";
    if (tag === "all" && sections.length) {
      toc = `<div class="toc-block"><h2>Trong số này</h2><ul>${tocEntries(sections)}</ul></div>`;
    }

    let empty = "";
    if (tag !== "all" && !sections.length) {
      empty = `<div class="empty-tag">${escapeHtml(
        EMPTY_TAG_COPY[tag] ||
          "Không có tin nào khớp bộ lọc này trong số báo đã chọn."
      )}</div>`;
    }

    const sectionHtml = renderSectionBlocks(sections);

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

  async function initReader() {
    const root = document.getElementById("paper-root");
    const status = document.getElementById("status");
    if (!root) return;

    let { date, tag } = parseParams();

    try {
      const index = await loadIndex();
      if (!date) date = index.latest;
      const data = await loadIssue(date);
      data.masthead = MASTHEAD;

      document.title = `${MASTHEAD} — ${data.date_vn || vnDate(data.date)}`;

      const render = (newTag) => {
        tag = newTag;
        syncUrl(date, tag);
        root.innerHTML = renderIssue(data, tag);
        renderTags(tag, render);
        location.hash = tag === "all" ? "" : `#tag=${tag}`;
      };

      render(tag);
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

    const index = await loadIndex();
    const dates = index.issues.map((i) => i.date).sort().reverse();

    listEl.innerHTML = dates
      .map((d) => {
        const latest = d === index.latest ? `<span class="badge">Mới nhất</span>` : "";
        return `<li>${latest}<a class="issue-link" href="${asset(`index.html?date=${d}`)}">${escapeHtml(issueListLabel(d, index))}</a>
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
    vnDate,
    MASTHEAD,
  };

  if (document.body.dataset.page === "reader") initReader();
  if (document.body.dataset.page === "archive") initArchive();
})();
