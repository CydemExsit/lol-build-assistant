const routesEl = document.querySelector("#routes");
const statusEl = document.querySelector("#status");
const activeChampionEl = document.querySelector("#activeChampion");
const enemyTeamEl = document.querySelector("#enemyTeam");
const sampleInfoEl = document.querySelector("#sampleInfo");
const sourceLineEl = document.querySelector("#sourceLine");
const constraintBadgeEl = document.querySelector("#constraintBadge");
const bootOptionsEl = document.querySelector("#bootOptions");
const refreshButton = document.querySelector("#refreshButton");
const snapshotButton = document.querySelector("#snapshotButton");
const snapshotSelect = document.querySelector("#snapshotSelect");

const itemIcon = (id) => `https://cdn5.lolalytics.com/item64/${id}.webp`;
let currentRoutes = [];
let pinnedRouteKey = null;

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`.trim();
}

function fmtPct(value) {
  if (typeof value !== "number") return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function fmtInt(value) {
  if (!Number.isFinite(Number(value))) return "-";
  return Number(value).toLocaleString("zh-TW");
}

function itemName(item) {
  return item?.display_name || item?.zh_tw_name || item?.name || "-";
}

function routeKey(route) {
  return (route.items || []).map((item) => item.item_id).join("-");
}

function isDuplicateRouteReason(reason) {
  return (
    reason.startsWith("LoLalytics Actually Built Sets 5") ||
    reason === "五件成裝組合完整出現在 LoLalytics 實際出裝資料中"
  );
}

function renderItem(item, options = {}) {
  const slot = document.createElement("div");
  slot.className = "item-slot";
  const img = document.createElement("img");
  img.src = itemIcon(item.item_id);
  img.alt = itemName(item);
  img.loading = "lazy";
  slot.title = `${itemName(item)} / ${item.name || ""} (${item.item_id})`;
  slot.append(img);
  if (options.showName !== false) {
    const name = document.createElement("div");
    name.className = "item-name";
    name.textContent = itemName(item);
    slot.append(name);
  }
  return slot;
}

function renderRoute(route, index, isPinned) {
  const article = document.createElement("article");
  article.className = `route ${index === 0 ? "primary" : ""} ${isPinned ? "pinned" : ""}`.trim();
  article.dataset.routeKey = routeKey(route);

  const meta = document.createElement("div");
  meta.className = "route-meta";
  const titleBar = document.createElement("div");
  titleBar.className = "route-title-bar";
  const title = document.createElement("div");
  title.className = "route-title";
  const idx = document.createElement("span");
  idx.className = "route-index";
  idx.textContent = String(index + 1);
  const heading = document.createElement("h3");
  heading.textContent = route.label || "推薦路線";
  title.append(idx, heading);

  const pinButton = document.createElement("button");
  pinButton.type = "button";
  pinButton.className = "route-pin";
  pinButton.setAttribute("aria-pressed", String(isPinned));
  pinButton.title = isPinned ? "恢復演算法原始排序" : "將這套出裝移到最上方";
  pinButton.textContent = isPinned ? "取消置頂" : "↑ 置頂";
  pinButton.addEventListener("click", () => {
    pinnedRouteKey = isPinned ? null : routeKey(route);
    renderRoutes(currentRoutes);
  });
  titleBar.append(title, pinButton);

  const stats = document.createElement("div");
  stats.className = "stats";
  const setStats = route.set_stats || {};
  const params = route.source?.lolalytics_params || {};
  stats.innerHTML = `
    <span>勝率 ${fmtPct(setStats.win_rate)} · 選取率 ${fmtPct(setStats.pick_rate)}</span>
    <span>${fmtInt(setStats.games)} 場 · window=${params.patch || "7"}</span>
    <span>${route.archetype || "balanced"} · score ${Number(route.score || 0).toFixed(2)}</span>
  `;
  meta.append(titleBar);
  for (const reminderText of route.starting_reminders || []) {
    const reminder = document.createElement("div");
    reminder.className = "route-reminder";
    reminder.setAttribute("role", "note");
    reminder.textContent = reminderText;
    meta.append(reminder);
  }
  meta.append(stats);

  const itemsArea = document.createElement("div");
  itemsArea.className = "items-area";
  const row = document.createElement("div");
  row.className = "slot-row";
  for (const item of route.items || []) row.append(renderItem(item));
  itemsArea.append(row);

  const reasons = document.createElement("ul");
  reasons.className = "reasons";
  const visibleReasons = (route.reasons || []).filter((reason) => !isDuplicateRouteReason(reason)).slice(0, 5);
  for (const reason of visibleReasons) {
    const li = document.createElement("li");
    li.textContent = reason;
    reasons.append(li);
  }

  article.append(meta, itemsArea, reasons);
  return article;
}

function renderRoutes(routes) {
  currentRoutes = [...routes];
  routesEl.innerHTML = "";
  if (!currentRoutes.length) {
    pinnedRouteKey = null;
    routesEl.innerHTML = '<div class="empty">沒有符合限制的五件成套</div>';
    return;
  }

  const pinnedIndex = currentRoutes.findIndex((route) => routeKey(route) === pinnedRouteKey);
  if (pinnedIndex < 0) pinnedRouteKey = null;
  const orderedRoutes = pinnedIndex > 0
    ? [currentRoutes[pinnedIndex], ...currentRoutes.filter((_, index) => index !== pinnedIndex)]
    : currentRoutes;

  orderedRoutes.forEach((route, index) => {
    const isPinned = routeKey(route) === pinnedRouteKey;
    routesEl.append(renderRoute(route, index, isPinned));
  });
}

function renderBootOptions(options) {
  bootOptionsEl.innerHTML = "";
  if (!options?.length) {
    bootOptionsEl.innerHTML = '<div class="empty">沒有鞋子候選</div>';
    return;
  }
  for (const [index, boot] of options.entries()) {
    const card = document.createElement("article");
    card.className = `boot-card ${index === 0 ? "primary" : ""}`.trim();
    const item = renderItem(boot, { showName: false });
    const detail = document.createElement("div");
    detail.className = "boot-detail";
    const title = document.createElement("div");
    title.className = "boot-title";
    title.textContent = `${index + 1}. ${itemName(boot)}`;
    const stats = document.createElement("dl");
    stats.className = "boot-stats";
    stats.innerHTML = `
      <div><dt>勝率</dt><dd>${fmtPct(boot.win_rate)}</dd></div>
      <div><dt>選取率</dt><dd>${fmtPct(boot.pick_rate)}</dd></div>
      <div><dt>場次</dt><dd>${fmtInt(boot.games)}</dd></div>
    `;
    detail.append(title, stats);
    card.append(item, detail);
    bootOptionsEl.append(card);
  }
}

function render(data) {
  if (!data) {
    currentRoutes = [];
    pinnedRouteKey = null;
    routesEl.innerHTML = '<div class="empty">尚未有推薦結果</div>';
    bootOptionsEl.innerHTML = "";
    return;
  }
  const active = data.active_player || {};
  const source = data.build?.source || {};
  activeChampionEl.textContent = `${active.champion_id || active.champion_name || "-"} (${active.position || "-"})`;
  sampleInfoEl.textContent = fmtInt(source.champions_analysed);
  sourceLineEl.textContent = `${source.lolalytics_params?.mode || "aram"} · ${source.lolalytics_params?.tier || "all"} · window=${source.lolalytics_params?.patch || "7"}`;
  constraintBadgeEl.textContent = source.built_sets_tab || "Actually Built Sets: 5";

  enemyTeamEl.innerHTML = "";
  for (const enemy of data.enemy_team || []) {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = enemy.champion || enemy.slug || "-";
    enemyTeamEl.append(pill);
  }

  renderBootOptions(data.build?.boot_options || []);

  const routes = data.build?.routes || [];
  renderRoutes(routes);
}

async function loadRecommendation() {
  const response = await fetch("/api/recommendation");
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || "讀取失敗");
  render(payload.data);
  setStatus(payload.data ? "已載入目前推薦" : "尚未產生推薦", payload.data ? "ok" : "");
}

async function loadSnapshots() {
  const response = await fetch("/api/snapshots");
  const payload = await response.json();
  if (!payload.ok) return;
  snapshotSelect.innerHTML = "";
  for (const snapshot of payload.snapshots || []) {
    const option = document.createElement("option");
    option.value = snapshot.path;
    option.textContent = snapshot.name;
    snapshotSelect.append(option);
  }
}

async function postJson(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || "執行失敗");
  return payload;
}

async function runLive() {
  refreshButton.disabled = true;
  snapshotButton.disabled = true;
  setStatus("抓取目前對局中...");
  try {
    const payload = await postJson("/api/recommend-live");
    render(payload.data);
    await loadSnapshots();
    setStatus(`已更新：${payload.snapshot}`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    refreshButton.disabled = false;
    snapshotButton.disabled = false;
  }
}

async function runSnapshot() {
  const snapshot = snapshotSelect.value;
  if (!snapshot) return;
  refreshButton.disabled = true;
  snapshotButton.disabled = true;
  setStatus("載入 snapshot 中...");
  try {
    const payload = await postJson("/api/recommend-snapshot", { snapshot });
    render(payload.data);
    setStatus(`已載入：${payload.snapshot}`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    refreshButton.disabled = false;
    snapshotButton.disabled = false;
  }
}

refreshButton.addEventListener("click", runLive);
snapshotButton.addEventListener("click", runSnapshot);

loadSnapshots().then(loadRecommendation).catch((error) => setStatus(error.message, "error"));
