"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const LEVEL = { junior: "جونیور", mid: "میدلول", senior: "سنیور", beginner: "مبتدی" };
const SRC_ICON = { maktabkhooneh: "🎓", coursera: "🎓", aparat: "▶", youtube: "▶" };
const COMP = { coverage: "پوشش مهارت‌های آگهی", role_fit: "هم‌خوانی با نقش", text: "شباهت متن", seniority: "تناسب سطح" };

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

const S = {
  meta: null, data: null, busy: false, tab: "roadmap", view: "list",
  filters: { city: "", seniority: "", remote: false }, jobs: null, jobsKey: "",
  quickSearch: "", picked: new Set(), profileSkills: null, profileSearch: "",
};

/* ------------------------------------------------------------ api */
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = "خطایی رخ داد؛ دوباره تلاش کن.";
    try { const j = await res.json(); if (typeof j.detail === "string" && /[؀-ۿ]/.test(j.detail)) msg = j.detail; } catch { /* ignore */ }
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return res.json();
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function toast(text) {
  const t = $("#toast"); t.textContent = text; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), 3800);
}

async function run(task) {
  if (S.busy) return;
  S.busy = true; renderChat(true);
  try { S.data = await task(); S.picked.clear(); S.quickSearch = ""; S.profileSkills = null; S.allRoles = false; }
  catch (e) {
    if (e.status === 404) { await newSession(); toast("نشست قبلی منقضی شده بود؛ از نو شروع کردیم."); }
    else toast(e.message);
  }
  finally { S.busy = false; render(); }
}

/* ------------------------------------------------------------ session */
async function newSession() {
  S.data = await post("/api/session", {});
  store.set("masir.sid", S.data.session_id);
  S.jobs = null; S.jobsKey = "";
}

async function boot() {
  applyTheme(store.get("masir.theme"));
  S.meta = await api("/api/meta");
  const sid = store.get("masir.sid");
  try { S.data = sid ? await api(`/api/session/${encodeURIComponent(sid)}`) : null; } catch { S.data = null; }
  if (!S.data) await newSession();
  $("#sampleList").innerHTML = S.meta.samples.map((s) => `<button type="button" data-sample="${esc(s.id)}">${esc(s.label)}</button>`).join("");
  render();
}

/* ------------------------------------------------------------ render */
function render() {
  const d = S.data;
  const mode = $("#mode");
  mode.textContent = S.meta.mode === "api" ? "هوش مصنوعی متصل" : "حالت آفلاین";
  mode.className = "pill" + (S.meta.mode === "api" ? " on" : "");
  mode.title = S.meta.mode === "api" ? (S.meta.model || "") : "بدون کلید API؛ استخراج با قواعد ساده";
  const done = !!d.roadmap;
  $("#progressBar").style.width = `${done ? 100 : (d.question / d.max_questions) * 100}%`;
  $("#progressText").textContent = done ? "پروفایلت کامل است" : `سؤال ${fa(Math.max(d.question, 1))} از ${fa(d.max_questions)}`;
  renderChat(false);
  renderQuick();
  renderTabs();
}

function renderChat(typing) {
  const box = $("#messages");
  const msgs = S.data.messages.map((m) => `<div class="msg ${m.role === "user" ? "user" : "assistant"}">${esc(m.text)}</div>`);
  S.data.warnings.forEach((w) => msgs.push(`<div class="msg notice">${esc(w)}</div>`));
  if (typing) msgs.push(`<div class="typing"><i></i><i></i><i></i></div>`);
  box.innerHTML = msgs.join("");
  box.scrollTop = box.scrollHeight;
  $("#sendBtn").disabled = typing;
  $("#quick").style.opacity = typing ? ".5" : "1";
}

function renderQuick() {
  const q = S.data.quick, el = $("#quick");
  if (!q) { el.innerHTML = ""; return; }
  if (q.type === "choices") {
    el.innerHTML = `<div class="chips">${q.options.map((o) => `<button class="chip-btn" data-say="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
  } else if (q.type === "roles") {
    const term = S.quickSearch.trim();
    const roles = q.roles.filter((r) => !term || r.label.includes(term) || r.domain.includes(term));
    const showAll = !q.suggested.length || S.allRoles;
    el.innerHTML = `
      ${q.suggested.length ? `<p class="quick-label">پیشنهاد بر اساس مهارت‌هایت</p>
        <div class="chips">${q.suggested.map((r) => `<button class="chip-btn on" data-say="${esc(r.label)}">${esc(r.label)} <small>${fa(r.fit)}٪</small></button>`).join("")}
        ${showAll ? "" : '<button class="chip-btn" data-act="allroles">همهٔ شغل‌ها…</button>'}</div>` : ""}
      ${showAll ? `<div class="picker">
        <input class="search" id="quickSearch" placeholder="جست‌وجوی شغل…" value="${esc(S.quickSearch)}">
        <div class="chips">${roles.map((r) => `<button class="chip-btn" data-say="${esc(r.label)}" title="${esc(r.domain)}">${esc(r.label)}</button>`).join("") || '<span class="muted">شغلی با این نام پیدا نشد؛ می‌توانی آن را بنویسی.</span>'}</div>
      </div>` : ""}`;
  } else if (q.type === "skills") {
    const term = S.quickSearch.trim().toLowerCase();
    const skills = q.skills.filter((s) => !term || s.label.toLowerCase().includes(term));
    el.innerHTML = `
      <div class="picker">
        <input class="search" id="quickSearch" placeholder="جست‌وجوی مهارت…" value="${esc(S.quickSearch)}">
        <div class="chips">${skills.map((s) => `<button class="chip-btn ${S.picked.has(s.id) ? "on" : ""}" data-pick="${esc(s.id)}">${esc(s.label)}</button>`).join("")}</div>
      </div>
      <div class="row">
        <button class="btn small" data-act="skills" ${S.picked.size ? "" : "disabled"}>ثبت ${S.picked.size ? fa(S.picked.size) + " مهارت" : "مهارت‌ها"}</button>
        <button class="btn ghost small" data-act="noskills">با هیچ‌کدام کار نکرده‌ام</button>
      </div>
      <p class="quick-label">فقط چیزهایی که واقعاً با آن‌ها کار کرده‌ای؛ «فقط اسمش را شنیده‌ام» حساب نمی‌شود.</p>`;
  } else if (q.type === "confirm") {
    el.innerHTML = `<div class="row"><button class="btn small" data-say="بله">بله، درست است</button>
      <button class="btn ghost small" data-act="edit">ویرایش اطلاعات</button></div>`;
  }
  const search = $("#quickSearch");
  if (search && S.focusQuick) { search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
}

function renderTabs() {
  $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === S.tab));
  ["roadmap", "jobs", "profile"].forEach((t) => ($(`#tab-${t}`).hidden = t !== S.tab));
  renderRoadmap();
  renderProfile();
  if (S.tab === "jobs") loadJobs(); else $("#jobsCount").textContent = S.jobs ? fa(S.jobs.length) : "";
}

/* ------------------------------------------------------------ roadmap */
const ICON_MAP = `<svg viewBox="0 0 24 24"><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14"/></svg>`;
const ICON_BRIEF = `<svg viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/></svg>`;

function ring(pct, cls = "") {
  const r = 26, c = 2 * Math.PI * r, off = c * (1 - Math.max(0, Math.min(1, pct / 100)));
  return `<div class="ring ${cls}"><svg viewBox="0 0 64 64"><circle class="track" cx="32" cy="32" r="${r}"/>
    <circle class="val" cx="32" cy="32" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${off}"/></svg><span>${fa(Math.round(pct))}</span></div>`;
}

function resourceItem(r) {
  const tags = [r.language === "fa" ? "فارسی" : "انگلیسی", r.is_free ? "رایگان" : "غیررایگان"];
  if (!r.accessible_from_iran) tags.push("ممکن است از ایران باز نشود");
  return `<li><span class="ico">${SRC_ICON[r.source] || "🔗"}</span><div>
    <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>
    <div class="meta">${esc(r.provider || r.source)} · ${tags.join(" · ")}</div></div></li>`;
}

function stepsList(rm) {
  const label = Object.fromEntries(rm.steps.map((s) => [s.id, s.label]));
  return `<ol class="timeline">${rm.steps.map((s, i) => `
    <li class="step"><span class="num">${fa(i + 1)}</span><div class="step-card">
      <div class="step-title"><strong>${esc(s.label)}</strong><span class="tag ${s.level}">${LEVEL[s.level]}</span></div>
      ${s.after.length ? `<p class="after">بعد از: ${s.after.map((a) => esc(label[a] || a)).join("، ")}</p>` : ""}
      ${s.resources.length ? `<ul class="res">${s.resources.map(resourceItem).join("")}</ul>` : '<p class="after">منبع تأییدشده‌ای برای این مورد ثبت نشده است.</p>'}
    </div></li>`).join("")}</ol>`;
}

function graphHtml(rm) {
  const depth = {};
  const after = Object.fromEntries(rm.steps.map((s) => [s.id, s.after]));
  const d = (id) => depth[id] ?? (depth[id] = after[id].length ? 1 + Math.max(...after[id].map(d)) : 0);
  rm.steps.forEach((s) => d(s.id));
  const cols = [];
  rm.steps.forEach((s, i) => (cols[depth[s.id]] ||= []).push(`<div class="gnode" data-node="${esc(s.id)}"><b>${fa(i + 1)}</b><span>${esc(s.label)}</span></div>`));
  return `<div class="graph-wrap"><div class="graph" id="graph"><svg class="edges"></svg>${cols.map((c) => `<div class="col">${c.join("")}</div>`).join("")}</div></div>`;
}

function drawEdges(root, edges) {
  const graph = $("#graph", root); if (!graph || !graph.offsetWidth) return;
  const box = graph.getBoundingClientRect(), svg = $("svg.edges", graph);
  svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
  svg.innerHTML = edges.map(([a, b]) => {
    const na = $(`[data-node="${CSS.escape(a)}"]`, graph), nb = $(`[data-node="${CSS.escape(b)}"]`, graph);
    if (!na || !nb) return "";
    const ra = na.getBoundingClientRect(), rb = nb.getBoundingClientRect();
    const x1 = ra.left - box.left, y1 = ra.top + ra.height / 2 - box.top, x2 = rb.right - box.left, y2 = rb.top + rb.height / 2 - box.top;
    const mx = (x1 + x2) / 2;
    return `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
  }).join("");
}

function renderRoadmap() {
  const el = $("#tab-roadmap"), rm = S.data.roadmap;
  if (!rm) {
    el.innerHTML = `<div class="empty">${ICON_MAP}<h3>نقشهٔ راهت اینجا ساخته می‌شود</h3>
      <p>به چند سؤال کوتاه جواب بده یا رزومه‌ات را با دکمهٔ 📎 بفرست. مسیر از گراف مهارت‌ها محاسبه می‌شود، نه حدس هوش مصنوعی.</p></div>`;
    return;
  }
  const pct = rm.total ? (100 * rm.known.length) / rm.total : 0;
  el.innerHTML = `
    <div class="summary-card">${ring(pct)}
      <div class="info"><h3>${esc(rm.role.label)} · ${LEVEL[rm.level]}</h3>
        <div class="stats"><span><b>${fa(rm.total)}</b> مهارت در این مسیر</span><span><b>${fa(rm.known.length)}</b> بلدی</span><span><b>${fa(rm.steps.length)}</b> قدم مانده</span></div>
      </div></div>
    ${rm.known.length ? `<div class="section"><h4>چیزهایی که بلدی</h4><div class="skills">${rm.known.map((k) => `<span class="skill ok">✓ ${esc(k.label)}</span>`).join("")}</div></div>` : ""}
    ${rm.steps.length ? `
      <div class="toolbar"><h4 style="margin:0">قدم‌های پیشنهادی</h4>
        <div class="seg"><button data-view="list" class="${S.view === "list" ? "on" : ""}">فهرست</button><button data-view="graph" class="${S.view === "graph" ? "on" : ""}">گراف</button></div></div>
      <div id="roadmapBody">${S.view === "graph" ? graphHtml(rm) : stepsList(rm)}</div>
      <p class="muted" style="margin-top:12px">ترتیب قدم‌ها از پیش‌نیازها محاسبه شده و منابع فقط از فهرست لینک‌های بررسی‌شده می‌آیند. اگر مهارتی را اشتباه گفته‌ای، در گفتگو بنویس؛ مثلاً «من اکسل بلد نیستم».</p>
      <div class="row" style="margin-top:12px"><button class="btn ghost small" data-act="dl-txt">دریافت خلاصه</button><button class="btn ghost small" data-act="dl-json">دریافت JSON</button></div>`
      : `<div class="empty"><h3>همهٔ مهارت‌های این مسیر را داری 🎉</h3><p>سطح بالاتری را امتحان کن.</p></div>`}`;
  if (S.view === "graph") requestAnimationFrame(() => drawEdges(el, rm.edges));
}

/* ------------------------------------------------------------ jobs */
function jobsKey() {
  const d = S.data;
  return JSON.stringify([d.session_id, d.profile.known.map((k) => k.id), d.profile.target_role?.id, d.profile.experience_years, !!d.resume, S.filters]);
}

async function loadJobs() {
  const el = $("#tab-jobs");
  if (!S.data.has_jobs) {
    el.innerHTML = `<div class="empty">${ICON_BRIEF}<h3>فرصت‌های شغلی مناسب تو</h3>
      <p>رزومه‌ات را با 📎 بفرست یا در گفتگو بگو چه کاری بلدی تا از بین ${fa(S.meta.counts.jobs)} آگهی واقعی، مناسب‌ترین‌ها را با دلیلش ببینی.</p>
      <button class="btn small" data-act="attach">افزودن رزومه</button></div>`;
    return;
  }
  const key = jobsKey();
  if (S.jobsKey !== key) {
    S.jobsKey = key;
    el.innerHTML = filtersHtml() + `<p class="muted">در حال پیدا کردن آگهی‌ها…</p>`;
    try {
      const f = S.filters, qs = new URLSearchParams({ city: f.city, seniority: f.seniority, remote: f.remote });
      const res = await api(`/api/jobs/${encodeURIComponent(S.data.session_id)}?${qs}`);
      if (S.jobsKey !== key) return;
      S.jobs = res.jobs; S.jobsBasis = res.based_on;
    } catch (e) { S.jobsKey = ""; toast(e.message); return; }
  }
  $("#jobsCount").textContent = S.jobs ? fa(S.jobs.length) : "";
  el.innerHTML = filtersHtml() +
    `<p class="based-on">${S.jobsBasis === "resume" ? "بر اساس رزومه و پروفایلت" : "بر اساس پروفایل گفتگو؛ با افزودن رزومه دقیق‌تر می‌شود"} · ${fa(S.meta.counts.jobs)} آگهی بررسی شد</p>` +
    (S.jobs.length ? `<div class="jobs">${S.jobs.map(jobCard).join("")}</div>` : `<div class="empty"><h3>آگهی‌ای با این فیلترها نیست</h3><p>فیلترها را کم‌تر کن.</p></div>`);
}

function filtersHtml() {
  const f = S.filters;
  return `<div class="filters">
    <select data-filter="city" aria-label="شهر"><option value="">همهٔ شهرها</option>${S.meta.cities.map((c) => `<option ${c === f.city ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
    <select data-filter="seniority" aria-label="سطح"><option value="">همهٔ سطوح</option>${["junior", "mid", "senior"].map((l) => `<option value="${l}" ${l === f.seniority ? "selected" : ""}>${LEVEL[l]}</option>`).join("")}</select>
    <label class="switch"><input type="checkbox" data-filter="remote" ${f.remote ? "checked" : ""}>فقط دورکاری</label></div>`;
}

function skillChips(list, cls, max) {
  const shown = list.slice(0, max).map((s) => `<span class="skill ${cls}">${cls === "ok" ? "✓" : "+"} ${esc(s.label)}</span>`).join("");
  return shown + (list.length > max ? `<span class="skill neutral">${fa(list.length - max)} مورد دیگر</span>` : "");
}

function jobCard(j) {
  const where = [j.company || "شرکت نامشخص", j.city].filter(Boolean).map(esc).join(" · ");
  return `<article class="job">
    <div class="job-main"><h4>${esc(j.title)}</h4>
      <div class="where">${where}${j.seniority ? `<span class="tag ${j.seniority}">${LEVEL[j.seniority]}</span>` : ""}${j.remote ? '<span class="tag">دورکاری</span>' : ""}</div></div>
    ${ring(j.score, "match")}
    <p class="why">${esc(j.explanation)}</p>
    <div class="skills">${skillChips(j.matched, "ok", 6)}${skillChips(j.missing, "miss", 6)}</div>
    <div class="breakdown" hidden>${Object.entries(j.components).map(([k, v]) => `<div class="bar">${COMP[k]} · ${fa(Math.round(v * 100))}٪<i><b style="width:${Math.round(v * 100)}%"></b></i></div>`).join("")}</div>
    <div class="actions">
      <a class="btn small" href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">مشاهدهٔ آگهی</a>
      ${j.missing.length ? `<button class="btn ghost small" data-gap="${esc(j.id)}" data-title="${esc(j.title)}">نقشهٔ راه این شغل</button>` : ""}
      <button class="btn ghost small" data-act="why">چرا این امتیاز؟</button>
    </div></article>`;
}

async function openGap(id, title) {
  openModal(title, `<p class="muted">در حال ساخت نقشهٔ راه…</p>`);
  try {
    const rm = await api(`/api/gap/${encodeURIComponent(S.data.session_id)}/${encodeURIComponent(id)}`);
    $("#modalBody").innerHTML = rm.steps.length
      ? `<p class="muted" style="margin-bottom:14px">مهارت‌هایی که این آگهی می‌خواهد و هنوز نداری، با پیش‌نیازهایشان و به ترتیب پیشنهادی:</p>${stepsList(rm)}`
      : `<div class="empty"><h3>همهٔ مهارت‌های این آگهی را داری</h3></div>`;
  } catch (e) { $("#modalBody").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

/* ------------------------------------------------------------ profile */
function renderProfile() {
  const el = $("#tab-profile"), d = S.data, p = d.profile;
  if (S.profileSkills === null) S.profileSkills = new Set(p.known.map((k) => k.id));
  const opt = (list, val, ph) => `<option value="">${ph}</option>` + list.map(([k, v]) => `<option value="${esc(k)}" ${k === val ? "selected" : ""}>${esc(v)}</option>`).join("");
  el.innerHTML = `
    ${d.resume ? `<div class="section"><h4>از رزومه‌ات</h4><dl class="kv">
      <dt>سابقه</dt><dd>${d.resume.years != null ? fa(d.resume.years) + " سال" : "—"}</dd>
      <dt>تحصیلات</dt><dd>${esc(d.resume.education.join("، ") || "—")}</dd>
      <dt>شهر</dt><dd>${esc(d.resume.location || "—")}</dd>
      ${d.resume.previous_roles.length ? `<dt>نقش‌های قبلی</dt><dd>${esc(d.resume.previous_roles.join("، "))}</dd>` : ""}</dl></div>` : ""}
    <div class="section"><h4>پروفایل تو</h4>
      <form class="form" id="profileForm">
        <div class="field"><label>شغل هدف</label><select name="target_role">${opt(S.meta.roles.map((r) => [r.id, `${r.label} — ${r.domain}`]), p.target_role?.id, "انتخاب کن…")}</select></div>
        <div class="field"><label>سطح هدف</label><select name="target_level">${opt([["junior", "جونیور"], ["mid", "میدلول"], ["senior", "سنیور"]], p.target_level, "انتخاب کن…")}</select></div>
        <div class="field"><label>سطح فعلی</label><select name="current_level">${opt([["beginner", "مبتدی"], ["junior", "جونیور"], ["mid", "میدلول"], ["senior", "سنیور"]], p.current_level, "انتخاب کن…")}</select></div>
        <div class="field"><label>سال سابقه</label><input name="experience_years" type="number" min="0" max="60" step="0.5" value="${p.experience_years ?? ""}"></div>
        <div class="field full"><label>تحصیلات یا دوره‌ها</label><input name="education" value="${esc(p.education || "")}" placeholder="مثلاً کارشناسی کامپیوتر"></div>
        <div class="field full"><label>مهارت‌هایی که با آن‌ها کار کرده‌ای</label>
          <div class="picker"><input class="search" id="profileSearch" placeholder="جست‌وجو و افزودن مهارت…" value="${esc(S.profileSearch)}">
            <div class="chips" id="profileChips">${profileChipsHtml()}</div></div></div>
        <div class="field full"><div class="row"><button class="btn" type="submit">ذخیره و ساخت نقشهٔ راه</button></div></div>
      </form></div>
    <div class="section"><h4>مصرف این نشست</h4><p class="muted">${fa(d.usage.calls)} درخواست به هوش مصنوعی · ${fa(d.usage.prompt_tokens + d.usage.completion_tokens)} توکن${d.usage.cost_usd != null ? ` · ${d.usage.cost_usd.toFixed(4)} دلار` : ""}${d.usage.calls ? ` · آخرین پاسخ در ${fa(Math.round(d.usage.latency_ms))} میلی‌ثانیه` : ""}</p></div>`;
}

function profileChipsHtml() {
  const term = S.profileSearch.trim().toLowerCase();
  const visible = S.meta.concepts.filter((c) => S.profileSkills.has(c.id) || (term && c.label.toLowerCase().includes(term))).slice(0, 80);
  return visible.map((c) => `<button type="button" class="chip-btn ${S.profileSkills.has(c.id) ? "on" : ""}" data-skill="${esc(c.id)}">${esc(c.label)}</button>`).join("")
    || '<span class="muted">برای افزودن، نام مهارت را جست‌وجو کن.</span>';
}

/* ------------------------------------------------------------ modal / upload */
function openModal(title, html) { $("#modalTitle").textContent = title; $("#modalBody").innerHTML = html; $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; }

function withConsent(next) {
  if (store.get("masir.consent") === "1") return next();
  openModal("پیش از ارسال رزومه", `
    <p>رزومه‌ات فقط برای ساختن پروفایل و پیدا کردن آگهی‌های مناسب، در حافظهٔ همین نشست پردازش می‌شود.</p>
    <ul class="muted" style="line-height:2">
      <li>روی دیسک یا در لاگ‌ها ذخیره نمی‌شود.</li>
      <li>${S.meta.mode === "api" ? "برای استخراج اطلاعات فقط به درگاه هوش مصنوعی فرستاده می‌شود." : "در حالت آفلاین به هیچ سرویسی فرستاده نمی‌شود."}</li>
      <li>با «شروع دوباره» از حافظه پاک می‌شود.</li></ul>
    <div class="row" style="margin-top:14px"><button class="btn" id="consentYes">موافقم</button><button class="btn ghost" id="consentNo">انصراف</button></div>`);
  $("#consentYes").onclick = () => { store.set("masir.consent", "1"); closeModal(); next(); };
  $("#consentNo").onclick = closeModal;
}

function sendResume(form) {
  form.append("session_id", S.data.session_id);
  S.tab = S.tab === "profile" ? "roadmap" : S.tab;
  run(() => api("/api/resume", { method: "POST", body: form }));
}

function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ------------------------------------------------------------ theme */
function applyTheme(t) {
  const theme = t || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = theme;
}

/* ------------------------------------------------------------ events */
document.addEventListener("click", (e) => {
  const t = e.target.closest("button, [data-act]");
  if (!t) { if (!e.target.closest(".attach-wrap")) $("#attachMenu").hidden = true; return; }
  if (t.dataset.say) return run(() => post("/api/chat", { session_id: S.data.session_id, text: t.dataset.say }));
  if (t.dataset.pick) { S.picked.has(t.dataset.pick) ? S.picked.delete(t.dataset.pick) : S.picked.add(t.dataset.pick); S.focusQuick = false; return renderQuick(); }
  if (t.id !== "attachBtn" && !t.closest("#attachMenu")) $("#attachMenu").hidden = true;
  if (t.dataset.skill) { const s = S.profileSkills; s.has(t.dataset.skill) ? s.delete(t.dataset.skill) : s.add(t.dataset.skill); $("#profileChips").innerHTML = profileChipsHtml(); return; }
  if (t.dataset.tab) { S.tab = t.dataset.tab; switchPane("results"); return renderTabs(); }
  if (t.dataset.view) { S.view = t.dataset.view; return renderRoadmap(); }
  if (t.dataset.gap) return openGap(t.dataset.gap, t.dataset.title);
  if (t.dataset.sample) { $("#attachMenu").hidden = true; const f = new FormData(); f.append("sample", t.dataset.sample); return withConsent(() => sendResume(f)); }
  if (t.dataset.pane) return switchPane(t.dataset.pane);
  switch (t.dataset.act || t.dataset.action || t.id) {
    case "allroles": S.allRoles = true; return renderQuick();
    case "skills": return run(() => post("/api/skills", { session_id: S.data.session_id, skills: [...S.picked] }));
    case "noskills": return run(() => post("/api/skills", { session_id: S.data.session_id, skills: [] }));
    case "edit": S.tab = "profile"; switchPane("results"); return renderTabs();
    case "why": { const b = t.closest(".job").querySelector(".breakdown"); b.hidden = !b.hidden; return; }
    case "attach": case "attachBtn": $("#attachMenu").hidden = !$("#attachMenu").hidden; switchPane("chat"); return;
    case "upload": $("#attachMenu").hidden = true; return withConsent(() => $("#fileInput").click());
    case "dl-txt": return download("roadmap.txt", S.data.roadmap.summary, "text/plain;charset=utf-8");
    case "dl-json": return download("roadmap.json", JSON.stringify(S.data.roadmap, null, 2), "application/json");
    case "modalClose": return closeModal();
    case "themeBtn": { const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; store.set("masir.theme", next); applyTheme(next); if (S.view === "graph") renderRoadmap(); return; }
    case "resetBtn":
      openModal("شروع دوباره", `<p>گفتگو، پروفایل و رزومهٔ این نشست پاک می‌شود.</p>
        <div class="row" style="margin-top:14px"><button class="btn" data-act="reset-yes">پاک کن و از نو شروع کن</button><button class="btn ghost" data-act="modalClose">انصراف</button></div>`);
      return;
    case "reset-yes":
      closeModal(); S.tab = "roadmap"; S.jobs = null; S.jobsKey = ""; S.view = "list";
      return run(() => post(`/api/reset/${encodeURIComponent(S.data.session_id)}`, {}).then((d) => { store.set("masir.sid", d.session_id); return d; }));
  }
});

document.addEventListener("input", (e) => {
  if (e.target.id === "quickSearch") { S.quickSearch = e.target.value; S.focusQuick = true; renderQuick(); }
  if (e.target.id === "profileSearch") { S.profileSearch = e.target.value; $("#profileChips").innerHTML = profileChipsHtml(); }
  if (e.target.id === "input") { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px"; }
});

document.addEventListener("change", (e) => {
  const f = e.target.dataset.filter;
  if (f) { S.filters[f] = f === "remote" ? e.target.checked : e.target.value; loadJobs(); }
  if (e.target.id === "fileInput" && e.target.files[0]) {
    const file = e.target.files[0]; e.target.value = "";
    if (file.size > 2_000_000) return toast("حجم فایل باید کمتر از ۲ مگابایت باشد.");
    const form = new FormData(); form.append("file", file); sendResume(form);
  }
});

document.addEventListener("submit", (e) => {
  e.preventDefault();
  if (e.target.id === "composer") {
    const input = $("#input"), text = input.value.trim();
    if (!text) return;
    input.value = ""; input.style.height = "auto";
    S.data.messages.push({ role: "user", text });
    return run(() => post("/api/chat", { session_id: S.data.session_id, text }));
  }
  if (e.target.id === "profileForm") {
    const f = new FormData(e.target), get = (k) => (f.get(k) || "").toString().trim();
    const body = { session_id: S.data.session_id, target_role: get("target_role"), target_level: get("target_level"),
      current_level: get("current_level"), education: get("education") || "—", experience_years: parseFloat(get("experience_years")),
      known_concepts: [...S.profileSkills] };
    if (!body.target_role || !body.target_level || !body.current_level || Number.isNaN(body.experience_years))
      return toast("شغل هدف، سطح‌ها و سال سابقه را کامل کن.");
    S.tab = "roadmap";
    return run(() => post("/api/profile", body));
  }
});

$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); }
});
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeModal(); $("#attachMenu").hidden = true; } });
window.addEventListener("resize", () => { if (S.view === "graph" && S.data?.roadmap) drawEdges($("#tab-roadmap"), S.data.roadmap.edges); });

function switchPane(p) {
  $(".workspace").dataset.pane = p;
  $$("#mobileSwitch button").forEach((b) => b.classList.toggle("active", b.dataset.pane === p));
}

switchPane("chat");
boot().catch(() => toast("اتصال به سرور برقرار نشد."));
