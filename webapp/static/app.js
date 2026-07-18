// State
let state = {
  deck: "",
  filter: "pending",
  cards: [],
  cardsOriginal: [],
  filteredCards: [],
  levelFilter: new Set(),
  tagFilter: new Set(),
  searchQuery: "",
  currentIdx: 0,
  currentTab: "front",
  ankiAvailable: false,
  shuffled: false,
  session: { accepted: 0, rejected: 0, skipped: 0 },
};

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  await loadDecks();
  await checkAnki();

  document.getElementById("deck-select").addEventListener("change", e => {
    state.deck = e.target.value;
    state.session = { accepted: 0, rejected: 0, skipped: 0 };
    renderSessionStats();
    if (state.deck) loadCards();
  });

  // Status pills
  document.querySelectorAll(".pill-status").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".pill-status").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.filter = pill.dataset.value;
      if (state.deck) loadCards();
    });
  });

  // Level pills (multi-select client-side)
  document.querySelectorAll(".pill-level").forEach(pill => {
    pill.addEventListener("click", () => {
      pill.classList.toggle("active");
      const val = pill.dataset.value;
      if (state.levelFilter.has(val)) state.levelFilter.delete(val);
      else state.levelFilter.add(val);
      applyFilters();
    });
  });

  // Clear tags
  document.getElementById("clear-tags-btn").addEventListener("click", clearTags);

  // Shuffle
  document.getElementById("shuffle-btn").addEventListener("click", toggleShuffle);

  // Push to Anki
  document.getElementById("push-btn").addEventListener("click", pushToAnki);

  // Search — debounced 120ms
  let searchTimer;
  document.getElementById("search-input").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.searchQuery = e.target.value.trim().toLowerCase();
      applyFilters();
    }, 120);
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", e => {
    const inInput = e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT";
    if (e.key === "Escape") {
      if (document.getElementById("shortcut-overlay").classList.contains("visible")) {
        hideShortcuts();
        return;
      }
      if (inInput) {
        e.target.blur();
        if (e.target.id === "search-input") {
          state.searchQuery = "";
          e.target.value = "";
          applyFilters();
        }
        return;
      }
    }
    if (inInput) return;
    if (e.key === "ArrowRight" || e.key === "l") navigate(1);
    if (e.key === "ArrowLeft"  || e.key === "h") navigate(-1);
    if (e.key === "a") review("accepted");
    if (e.key === "r") startReject();
    if (e.key === "s") review("skipped");
    if (e.key === "f" || e.key === " ") { e.preventDefault(); toggleTab(); }
    if (e.key === "?") { e.preventDefault(); toggleShortcuts(); }
    if (e.key === "/") { e.preventDefault(); document.getElementById("search-input").focus(); }
    if (e.key === "S") toggleShuffle();
  });

  // Shortcut overlay: click background to close
  document.getElementById("shortcut-overlay").addEventListener("click", e => {
    if (e.target.id === "shortcut-overlay") hideShortcuts();
  });
}

// ---------------------------------------------------------------------------
// Shortcut overlay
// ---------------------------------------------------------------------------

function toggleShortcuts() {
  document.getElementById("shortcut-overlay").classList.toggle("visible");
}

function hideShortcuts() {
  document.getElementById("shortcut-overlay").classList.remove("visible");
}

// ---------------------------------------------------------------------------
// Shuffle
// ---------------------------------------------------------------------------

function toggleShuffle() {
  const btn = document.getElementById("shuffle-btn");
  state.shuffled = !state.shuffled;
  btn.classList.toggle("active", state.shuffled);
  if (state.shuffled) {
    state.cardsOriginal = [...state.cards];
    fisherYates(state.cards);
  } else {
    state.cards = [...state.cardsOriginal];
  }
  applyFilters();
}

function fisherYates(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

// ---------------------------------------------------------------------------
// Session stats
// ---------------------------------------------------------------------------

function renderSessionStats() {
  document.getElementById("sess-a").textContent = state.session.accepted;
  document.getElementById("sess-r").textContent = state.session.rejected;
  document.getElementById("sess-s").textContent = state.session.skipped;
}

function bumpStat(action) {
  const map = { accepted: "sess-a", rejected: "sess-r", skipped: "sess-s" };
  const elId = map[action];
  if (!elId) return;
  state.session[action]++;
  const el = document.getElementById(elId);
  el.textContent = state.session[action];
  el.classList.remove("pop");
  void el.offsetWidth; // restart animation
  el.classList.add("pop");
}

// ---------------------------------------------------------------------------
// Decks
// ---------------------------------------------------------------------------

async function loadDecks() {
  const decks = await api("/api/decks");
  if (!decks) return;
  const sel = document.getElementById("deck-select");
  decks.forEach(d => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = d;
    sel.appendChild(opt);
  });
}

// ---------------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------------

async function loadCards() {
  const data = await api(`/api/cards/${state.deck}?filter=${state.filter}`);
  if (!data) return;
  state.cards = data.cards;
  state.cardsOriginal = [...state.cards];

  // Reset client-side filters when deck/status changes
  state.shuffled = false;
  document.getElementById("shuffle-btn").classList.remove("active");
  state.levelFilter.clear();
  state.tagFilter.clear();
  state.searchQuery = "";
  document.getElementById("search-input").value = "";
  document.querySelectorAll(".pill-level").forEach(p => p.classList.remove("active"));
  document.getElementById("clear-tags-btn").style.display = "none";

  renderProgress(data.counts);
  renderTagPills();
  applyFilters();
}

function renderTagPills() {
  const tagCounts = {};
  const skipTags = new Set(["senior", "mid-level", "junior", "cross-topic"]);
  state.cards.forEach(c => {
    (c.tags || []).forEach(t => {
      if (!skipTags.has(t)) tagCounts[t] = (tagCounts[t] || 0) + 1;
    });
  });
  const container = document.getElementById("tag-pills");
  container.innerHTML = "";
  Object.keys(tagCounts).sort().forEach(tag => {
    const pill = document.createElement("button");
    pill.className = "pill";
    pill.textContent = tag;
    pill.addEventListener("click", () => {
      pill.classList.toggle("active");
      if (state.tagFilter.has(tag)) state.tagFilter.delete(tag);
      else state.tagFilter.add(tag);
      document.getElementById("clear-tags-btn").style.display =
        state.tagFilter.size > 0 ? "" : "none";
      applyFilters();
    });
    container.appendChild(pill);
  });
}

function clearTags() {
  state.tagFilter.clear();
  document.querySelectorAll("#tag-pills .pill").forEach(p => p.classList.remove("active"));
  document.getElementById("clear-tags-btn").style.display = "none";
  applyFilters();
}

function applyFilters() {
  const { cards, levelFilter, tagFilter, searchQuery } = state;
  const skipTags = new Set(["senior", "mid-level", "junior", "cross-topic"]);

  state.filteredCards = cards.filter(card => {
    if (levelFilter.size > 0) {
      const hasLevel = (card.tags || []).some(t => levelFilter.has(t));
      if (!hasLevel) return false;
    }
    if (tagFilter.size > 0) {
      for (const t of tagFilter) {
        if (!(card.tags || []).includes(t)) return false;
      }
    }
    if (searchQuery) {
      const q = card.question.toLowerCase();
      const tags = (card.tags || []).join(" ").toLowerCase();
      if (!q.includes(searchQuery) && !tags.includes(searchQuery)) return false;
    }
    return true;
  });

  renderSidebar();

  if (state.filteredCards.length > 0) {
    state.currentIdx = 0;
    showCard(0);
  } else {
    document.getElementById("card-view").style.display = "none";
    document.getElementById("empty-state").style.display = "flex";
    document.getElementById("empty-state").textContent =
      cards.length === 0
        ? `No ${state.filter === "all" ? "" : state.filter + " "}cards in this deck.`
        : "No cards match the current filters.";
  }
}

function renderSidebar() {
  const list = document.getElementById("card-list");
  list.innerHTML = "";
  const q = state.searchQuery;
  state.filteredCards.forEach((card, idx) => {
    const el = document.createElement("div");
    el.className = "card-item" + (idx === state.currentIdx ? " active" : "");
    el.style.animationDelay = `${Math.min(idx * 28, 420)}ms`;
    el.dataset.idx = idx;

    let questionHtml = escHtml(card.question);
    if (q) {
      const re = new RegExp(escRegex(q), "gi");
      questionHtml = questionHtml.replace(re, m => `<mark>${m}</mark>`);
    }

    el.innerHTML = `
      <div class="status-dot dot-${card.status}"></div>
      <div>
        <div class="card-item-text">${questionHtml}</div>
        <div class="card-item-section">${escHtml(card.section)}</div>
      </div>`;
    el.addEventListener("click", () => showCard(idx));
    list.appendChild(el);
  });
}

function renderProgress(counts) {
  const total = (counts.pending || 0) + (counts.accepted || 0) + (counts.rejected || 0) + (counts.skipped || 0);
  const done  = (counts.accepted || 0) + (counts.rejected || 0);
  const pct   = total > 0 ? Math.round((done / total) * 100) : 0;
  document.getElementById("progress-bar").style.width = pct + "%";
  document.getElementById("progress-label").textContent = `${done}/${total} reviewed`;
}

// ---------------------------------------------------------------------------
// Show card
// ---------------------------------------------------------------------------

function showCard(idx) {
  if (idx < 0 || idx >= state.filteredCards.length) return;
  state.currentIdx = idx;
  state.currentTab = "front";

  document.querySelectorAll(".card-item").forEach((el, i) => {
    el.classList.toggle("active", i === idx);
  });
  const active = document.querySelector(".card-item.active");
  if (active) active.scrollIntoView({ block: "nearest" });

  const card = state.filteredCards[idx];

  document.getElementById("empty-state").style.display = "none";
  document.getElementById("card-view").style.display = "flex";

  document.getElementById("card-section").textContent = card.section;
  document.getElementById("card-type").textContent = card.card_type;
  const statusEl = document.getElementById("card-status");
  statusEl.textContent = card.status;
  statusEl.className = `badge badge-${card.status}`;

  // Tags + source_nodes
  const skipTags = new Set(["senior", "mid-level", "junior", "cross-topic"]);
  const tagsEl = document.getElementById("card-tags");
  tagsEl.innerHTML = "";

  const regularTags = (card.tags || []).filter(t => !skipTags.has(t));
  regularTags.forEach((t, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "tag-sep";
      sep.textContent = "·";
      tagsEl.appendChild(sep);
    }
    const span = document.createElement("span");
    span.className = "tag-plain";
    span.textContent = t;
    tagsEl.appendChild(span);
  });

  (card.source_nodes || []).forEach(slug => {
    const pill = document.createElement("span");
    pill.className = "source-pill";
    pill.textContent = slug;
    attachVaultPopover(pill, slug);
    tagsEl.appendChild(pill);
  });

  document.getElementById("reject-panel").style.display = "none";
  document.getElementById("reject-comment").value = card.comment || "";

  loadPreview("front");
  setTab("front");
}

// ---------------------------------------------------------------------------
// Preview
// ---------------------------------------------------------------------------

function loadPreview(side) {
  const card = state.filteredCards[state.currentIdx];
  if (!card) return;
  const frame = document.getElementById("preview-frame");
  const loader = document.getElementById("preview-loader");

  loader.classList.remove("hidden");
  frame.classList.add("loading");
  frame.src = `/api/preview/${state.deck}/${card.id}/${side}`;
  frame.onload = () => {
    loader.classList.add("hidden");
    frame.classList.remove("loading");
  };
}

function showTab(side) {
  state.currentTab = side;
  setTab(side);
  loadPreview(side);
}

function toggleTab() {
  showTab(state.currentTab === "front" ? "back" : "front");
}

function setTab(side) {
  document.getElementById("tab-front").classList.toggle("active", side === "front");
  document.getElementById("tab-back").classList.toggle("active", side === "back");
}

// ---------------------------------------------------------------------------
// Review actions
// ---------------------------------------------------------------------------

async function review(action) {
  const card = state.filteredCards[state.currentIdx];
  if (!card) return;
  await api(`/api/review/${state.deck}/${card.id}`, "POST", { action, comment: "" });
  card.status = action;
  bumpStat(action);
  flashBtn(action);
  updateCurrentCardUI();
  if (action === "accepted" || action === "skipped") navigate(1);
}

function flashBtn(action) {
  const map = { accepted: "btn-accept", rejected: "btn-reject", skipped: "btn-skip" };
  const cls = map[action];
  if (!cls) return;
  const btn = document.querySelector(`.actions .${cls}`);
  if (!btn) return;
  btn.classList.remove("flash");
  void btn.offsetWidth;
  btn.classList.add("flash");
}

function startReject() {
  document.getElementById("reject-panel").style.display = "flex";
  document.getElementById("reject-comment").focus();
}

function cancelReject() {
  document.getElementById("reject-panel").style.display = "none";
}

async function confirmReject() {
  const card = state.filteredCards[state.currentIdx];
  if (!card) return;
  const comment = document.getElementById("reject-comment").value.trim();
  await api(`/api/review/${state.deck}/${card.id}`, "POST", { action: "rejected", comment });
  card.status = "rejected";
  card.comment = comment;
  bumpStat("rejected");
  flashBtn("rejected");
  document.getElementById("reject-panel").style.display = "none";
  updateCurrentCardUI();
  navigate(1);
}

function updateCurrentCardUI() {
  const card = state.filteredCards[state.currentIdx];
  if (!card) return;
  const items = document.querySelectorAll(".card-item");
  const dot = items[state.currentIdx]?.querySelector(".status-dot");
  if (dot) dot.className = `status-dot dot-${card.status}`;
  const statusEl = document.getElementById("card-status");
  statusEl.textContent = card.status;
  statusEl.className = `badge badge-${card.status}`;
  // Recompute progress from all (unfiltered) cards
  const counts = { pending: 0, accepted: 0, rejected: 0, skipped: 0 };
  state.cards.forEach(c => { counts[c.status] = (counts[c.status] || 0) + 1; });
  renderProgress(counts);
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function navigate(delta) {
  const next = state.currentIdx + delta;
  if (next >= 0 && next < state.filteredCards.length) showCard(next);
}

// ---------------------------------------------------------------------------
// Vault popover
// ---------------------------------------------------------------------------

const _vaultCache = {};
let _vaultShowTimer = null;
let _vaultHideTimer = null;

function attachVaultPopover(pill, slug) {
  pill.addEventListener("mouseenter", () => {
    clearTimeout(_vaultHideTimer);
    clearTimeout(_vaultShowTimer);
    _vaultShowTimer = setTimeout(() => showVaultPopover(pill, slug), 400);
  });
  pill.addEventListener("mouseleave", () => {
    clearTimeout(_vaultShowTimer);
    _vaultHideTimer = setTimeout(hideVaultPopover, 250);
  });
}

async function showVaultPopover(pill, slug) {
  let info = _vaultCache[slug];
  if (!info) {
    const data = await api(`/api/vault/${slug}`);
    if (!data) return;
    _vaultCache[slug] = data;
    info = data;
  }

  const pop = document.getElementById("vault-popover");
  pop.querySelector(".vp-title").textContent = info.title || slug;
  pop.querySelector(".vp-excerpt").textContent = info.excerpt || "(no preview available)";
  pop.querySelector(".vp-link").href = `/vault/${slug}`;

  // Position: above the pill
  const rect = pill.getBoundingClientRect();
  let left = Math.round(rect.left);
  if (left + 272 > window.innerWidth - 12) left = window.innerWidth - 272 - 12;
  pop.style.left = left + "px";
  pop.style.top = (rect.top - 6) + "px";

  pop.onmouseenter = () => clearTimeout(_vaultHideTimer);
  pop.onmouseleave = () => { _vaultHideTimer = setTimeout(hideVaultPopover, 250); };

  pop.classList.add("visible");
}

function hideVaultPopover() {
  document.getElementById("vault-popover").classList.remove("visible");
}

// ---------------------------------------------------------------------------
// AnkiConnect
// ---------------------------------------------------------------------------

async function checkAnki() {
  const status = await api("/api/anki/status");
  if (!status) return;
  state.ankiAvailable = status.available;
  const dot = document.getElementById("anki-status");
  dot.className = `anki-dot ${status.available ? "anki-ok" : "anki-fail"}`;
  dot.title = status.available ? "AnkiConnect: connected" : "AnkiConnect: not available";
  document.getElementById("push-btn").disabled = !status.available || !state.deck;
}

async function pushToAnki() {
  if (!state.deck) return;
  const result = await api(`/api/anki/push/${state.deck}`, "POST");
  if (!result) return;
  alert(`Pushed ${result.pushed} cards to Anki.${result.errors?.length ? `\n${result.errors.length} errors.` : ""}`);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function api(url, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  try {
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      console.error("API error:", err);
      return null;
    }
    return resp.json();
  } catch (e) {
    console.error("Fetch error:", e);
    return null;
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ---------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", init);
// Exposed for inline onclick handlers in index.html
window.showTab = showTab;
window.navigate = navigate;
window.review = review;
window.startReject = startReject;
window.cancelReject = cancelReject;
window.confirmReject = confirmReject;
