const ui = {
  statusBar: document.querySelector("#statusBar"),
  serviceDot: document.querySelector("#serviceDot"),
  serviceState: document.querySelector("#serviceState"),
  emptyState: document.querySelector("#emptyState"),
  content: document.querySelector("#recommendationContent"),
  freezeState: document.querySelector("#freezeState"),
  generatedAt: document.querySelector("#generatedAt"),
  dataHealthBadge: document.querySelector("#dataHealthBadge"),
  activePortrait: document.querySelector("#activePortrait"),
  activeChampion: document.querySelector("#activeChampion"),
  allyTeam: document.querySelector("#allyTeam"),
  enemyTeam: document.querySelector("#enemyTeam"),
  sampleInfo: document.querySelector("#sampleInfo"),
  sourceLine: document.querySelector("#sourceLine"),
  compositionNotes: document.querySelector("#compositionNotes"),
  damageAnalysis: document.querySelector("#damageAnalysis"),
  damageLabel: document.querySelector("#damageLabel"),
  damagePressure: document.querySelector("#damagePressure"),
  damageMeter: document.querySelector("#damageMeter"),
  damageLegend: document.querySelector("#damageLegend"),
  defenseLabel: document.querySelector("#defenseLabel"),
  defensiveOptions: document.querySelector("#defensiveOptions"),
  bootOptions: document.querySelector("#bootOptions"),
  routes: document.querySelector("#routes"),
  constraintBadge: document.querySelector("#constraintBadge"),
  historyList: document.querySelector("#historyList"),
  historySummary: document.querySelector("#historySummary"),
  healthGrid: document.querySelector("#healthGrid"),
  snapshotSelect: document.querySelector("#snapshotSelect"),
  snapshotButton: document.querySelector("#snapshotButton"),
  refreshButton: document.querySelector("#refreshButton"),
  healthRefresh: document.querySelector("#healthRefresh"),
};

const state = {
  recommendation: null,
  service: null,
  health: null,
  history: [],
  lastRevision: null,
  polling: false,
};

const itemIcon = (id) => `https://cdn5.lolalytics.com/item64/${id}.webp`;
const championIcon = (championId) => {
  const version = state.health?.item_map?.ddragon_version || "16.14.1";
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${championId}.png`;
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function fmtPct(value, digits = 2) {
  return typeof value === "number" ? `${(value * 100).toFixed(digits)}%` : "-";
}

function fmtInt(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-TW") : "-";
}

function fmtBytes(value) {
  const size = Number(value);
  if (!Number.isFinite(size)) return "-";
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function itemName(item) {
  return item?.display_name || item?.zh_tw_name || item?.name || "-";
}

function routeKey(route) {
  return (route?.items || []).map((item) => item.item_id).join("-");
}

function currentMatchKey() {
  return state.recommendation?.session?.match_key || "";
}

function pinnedStorageKey() {
  return `lol-build-assistant:pin:${currentMatchKey()}`;
}

function getPinnedRoute() {
  return currentMatchKey() ? localStorage.getItem(pinnedStorageKey()) : null;
}

function setPinnedRoute(key) {
  if (!currentMatchKey()) return;
  if (key) localStorage.setItem(pinnedStorageKey(), key);
  else localStorage.removeItem(pinnedStorageKey());
}

function setStatus(message, type = "") {
  ui.statusBar.textContent = message || "";
  ui.statusBar.className = `status-bar ${type}`.trim();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function postJson(url, body) {
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function showView(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.classList.toggle("active", tab.dataset.view === name);
  }
  for (const panel of document.querySelectorAll("[data-view-panel]")) {
    const active = panel.dataset.viewPanel === name;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  }
  if (name === "history") loadHistory().catch(showError);
  if (name === "health") loadHealth().catch(showError);
}

function showError(error) {
  setStatus(error?.message || String(error), "error");
}

function image(src, alt, className = "") {
  const img = element("img", className);
  img.src = src;
  img.alt = alt;
  img.loading = "lazy";
  img.addEventListener("error", () => {
    img.style.visibility = "hidden";
  });
  return img;
}

function renderTeam(target, players, activeSlug = "") {
  target.replaceChildren();
  for (const player of players || []) {
    const champion = player.champion || player.champion_id || player.champion_name || "-";
    const slug = player.slug || player.champion_slug || String(champion).toLowerCase();
    const token = element("div", `champion-token ${player.is_active || slug === activeSlug ? "active" : ""}`.trim());
    token.title = champion;
    token.append(image(championIcon(champion), champion), element("span", "", champion));
    target.append(token);
  }
}

function renderBoots(options) {
  ui.bootOptions.replaceChildren();
  if (!options?.length) {
    ui.bootOptions.append(element("div", "empty", "沒有鞋子資料"));
    return;
  }
  options.forEach((boot, index) => {
    const card = element("article", "boot-card");
    const detail = element("div");
    detail.append(element("div", "boot-title", `${index + 1}. ${itemName(boot)}`));
    const stats = element("dl", "boot-stats");
    for (const [label, value] of [
      ["勝率", fmtPct(boot.win_rate)],
      ["選取率", fmtPct(boot.pick_rate)],
      ["場次", fmtInt(boot.games)],
    ]) {
      const cell = element("div");
      cell.append(element("dt", "", label), element("dd", "", value));
      stats.append(cell);
    }
    detail.append(stats);
    card.append(image(itemIcon(boot.item_id), itemName(boot)), detail);
    ui.bootOptions.append(card);
  });
}

function renderDamageAnalysis(analysis, defensiveOptions) {
  const mix = analysis?.damage_mix || {};
  const values = ["physical", "magic", "true"].map((key) => Number(mix[key]));
  const valid = values.every(Number.isFinite) && values.reduce((sum, value) => sum + value, 0) > 0;
  ui.damageAnalysis.hidden = !valid;
  if (!valid) return;

  ui.damageLabel.textContent = analysis.label || "傷害類型估算";
  ui.damagePressure.textContent = `整隊輸出權重 ${fmtPct(analysis.output_weight, 1)}`;
  ui.damageMeter.replaceChildren();
  ui.damageLegend.replaceChildren();

  [
    ["physical", "物理", Number(mix.physical)],
    ["magic", "魔法", Number(mix.magic)],
    ["true", "真實", Number(mix.true)],
  ].forEach(([key, label, value]) => {
    const segment = element("span", `damage-segment ${key}`);
    segment.style.width = `${Math.max(value * 100, 0)}%`;
    segment.title = `${label} ${fmtPct(value, 1)}`;
    ui.damageMeter.append(segment);

    const legend = element("div", "damage-legend-item");
    legend.append(
      element("span", `damage-swatch ${key}`),
      element("span", "", label),
      element("strong", "", fmtPct(value, 1)),
    );
    ui.damageLegend.append(legend);
  });

  ui.defenseLabel.textContent = analysis.defense_label || "暫無單一抗性需求";
  ui.defenseLabel.className = `defense-label ${analysis.defense_strength || "none"}`;
  ui.defensiveOptions.replaceChildren();
  for (const option of defensiveOptions || []) {
    const row = element("article", "defensive-option");
    const detail = element("div", "defensive-option-detail");
    const title = element("div", "defensive-option-title");
    title.append(
      element("strong", "", itemName(option)),
      element(
        "span",
        "defensive-kind",
        option.category === "pure_defense" ? "大型防裝" : "保留輸出",
      ),
    );
    detail.append(title, element("p", "", option.reason || ""));
    if (typeof option.win_rate === "number") {
      detail.append(
        element(
          "span",
          "defensive-stat",
          `勝率 ${fmtPct(option.win_rate)} · 選取率 ${fmtPct(option.pick_rate)} · ${fmtInt(option.games)} 場`,
        ),
      );
    }
    row.append(image(itemIcon(option.item_id), itemName(option)), detail);
    ui.defensiveOptions.append(row);
  }
}

function feedbackFor(matchKey, key) {
  const match = state.history.find((entry) => entry.match_key === matchKey);
  return match?.feedback?.find((entry) => entry.route_key === key)?.sentiment || 0;
}

function renderStarterOption(starter) {
  if (!starter?.items?.length) return null;
  const sourceLabels = {
    lolalytics_starting_items: "LoLalytics 起手",
    data_dragon_component_tree: "合成樹銜接",
    route_requirement: "路線需求",
  };
  const block = element("div", "route-starter");
  const header = element("div", "starter-header");
  header.append(
    element("strong", "", "起手銜接"),
    element("span", "muted", sourceLabels[starter.source] || "路線銜接"),
  );
  const content = element("div", "starter-content");
  const itemRow = element("div", "starter-items");
  starter.items.forEach((item, index) => {
    if (index > 0) itemRow.append(element("span", "starter-plus", "+"));
    const itemNode = element("div", "starter-item");
    itemNode.append(image(itemIcon(item.item_id), itemName(item)), element("span", "", itemName(item)));
    itemRow.append(itemNode);
  });
  const targetName = itemName(starter.target);
  const detailParts = [`${fmtInt(starter.total_gold)} 金`, `銜接 ${targetName}`];
  if (typeof starter.win_rate === "number") detailParts.push(`勝率 ${fmtPct(starter.win_rate)}`);
  content.append(itemRow, element("span", "starter-detail", detailParts.join(" · ")));
  block.append(header, content);
  return block;
}

async function saveFeedback(route, sentiment) {
  const matchKey = currentMatchKey();
  const key = routeKey(route);
  await postJson("/api/feedback", { match_key: matchKey, route_key: key, sentiment });
  await loadHistory();
  renderRoutes(state.recommendation?.build?.routes || []);
  setStatus(sentiment === 0 ? "已清除本套路回饋" : "已記錄本套路回饋", "ok");
}

function renderRoute(route, displayIndex, pinned) {
  const article = element("article", `route ${pinned ? "pinned" : ""}`.trim());
  const key = routeKey(route);
  const meta = element("div", "route-meta");
  const titleLine = element("div", "route-title-line");
  const heading = element("div", "route-heading");
  heading.append(element("span", "route-index", displayIndex + 1), element("h3", "", route.label || "成裝路線"));
  const pin = element("button", "pin-button", "↑");
  pin.type = "button";
  pin.title = pinned ? "取消置頂" : "置頂";
  pin.setAttribute("aria-label", pin.title);
  pin.setAttribute("aria-pressed", String(pinned));
  pin.addEventListener("click", () => {
    setPinnedRoute(pinned ? "" : key);
    renderRoutes(state.recommendation?.build?.routes || []);
  });
  titleLine.append(heading, pin);
  meta.append(titleLine);

  const confidence = route.confidence || {};
  const confidenceBadge = element("span", `confidence-badge ${confidence.level || ""}`.trim(), confidence.label || "樣本可信度未知");
  meta.append(confidenceBadge);

  const setStats = route.set_stats || {};
  const stats = element("div", "route-stats");
  for (const [label, value] of [
    ["勝率", fmtPct(setStats.win_rate)],
    ["選取率", fmtPct(setStats.pick_rate)],
    ["場次", fmtInt(setStats.games)],
  ]) {
    const cell = element("div");
    cell.append(element("span", "", label), element("strong", "", value));
    stats.append(cell);
  }
  meta.append(stats);

  const feedback = element("div", "feedback-control");
  const selected = feedbackFor(currentMatchKey(), key);
  const positive = element("button", selected > 0 ? "selected-positive" : "", "適合我");
  const negative = element("button", selected < 0 ? "selected-negative" : "", "不適合");
  positive.type = negative.type = "button";
  positive.addEventListener("click", () => saveFeedback(route, selected > 0 ? 0 : 1).catch(showError));
  negative.addEventListener("click", () => saveFeedback(route, selected < 0 ? 0 : -1).catch(showError));
  feedback.append(positive, negative);
  meta.append(feedback);

  const sequence = element("div", "route-sequence");
  sequence.append(element("div", "sequence-label", "成裝順序"));
  const itemRow = element("div", "item-sequence");
  (route.items || []).forEach((item, index) => {
    const itemNode = element("div", "route-item");
    itemNode.title = `${itemName(item)} / ${item.name || ""} (${item.item_id})`;
    itemNode.append(
      element("span", "order", index + 1),
      image(itemIcon(item.item_id), itemName(item)),
      element("span", "item-name", itemName(item)),
    );
    itemRow.append(itemNode);
  });
  sequence.append(itemRow);
  const starter = renderStarterOption(route.starter_option);
  if (starter) sequence.append(starter);
  if (route.starter_option?.source !== "route_requirement") {
    for (const reminderText of route.starting_reminders || []) {
      sequence.append(element("div", "route-reminder", reminderText));
    }
  }

  const reasonArea = element("div", "route-reason-area");
  const reasons = element("ul", "route-reasons");
  const visibleReasons = (route.reasons || [])
    .filter((reason) => !String(reason).startsWith("LoLalytics Actually Built Sets 5"))
    .slice(0, 5);
  for (const reason of visibleReasons) reasons.append(element("li", "", reason));
  reasonArea.append(reasons);
  article.append(meta, sequence, reasonArea);
  return article;
}

function renderRoutes(routes) {
  ui.routes.replaceChildren();
  if (!routes?.length) {
    ui.routes.append(element("div", "empty", "沒有符合限制的五件成裝路線"));
    return;
  }
  const pinnedKey = getPinnedRoute();
  const ordered = [...routes];
  const pinnedIndex = ordered.findIndex((route) => routeKey(route) === pinnedKey);
  if (pinnedIndex > 0) ordered.unshift(...ordered.splice(pinnedIndex, 1));
  ordered.forEach((route, index) => ui.routes.append(renderRoute(route, index, routeKey(route) === pinnedKey)));
}

function renderRecommendation(data) {
  state.recommendation = data;
  const hasData = Boolean(data);
  ui.emptyState.hidden = hasData;
  ui.content.hidden = !hasData;
  if (!hasData) return;

  const active = data.active_player || {};
  const source = data.build?.source || {};
  const session = data.session || {};
  const health = source.data_health || {};
  ui.freezeState.textContent = session.frozen ? "已凍結" : "未凍結";
  ui.generatedAt.textContent = `產生時間 ${fmtDate(session.generated_at)}`;
  ui.dataHealthBadge.textContent = health.label || "資料狀態未知";
  ui.dataHealthBadge.className = `health-badge ${health.level || ""}`.trim();
  ui.activeChampion.textContent = active.champion_name || active.champion_id || "-";
  ui.activePortrait.src = championIcon(active.champion_id || active.champion_slug || "");
  ui.activePortrait.alt = active.champion_name || active.champion_id || "";
  ui.activePortrait.style.visibility = "visible";
  ui.sampleInfo.textContent = fmtInt(source.champions_analysed);
  const params = source.lolalytics_params || {};
  ui.sourceLine.textContent = `${String(params.mode || "aram").toUpperCase()} · ${params.tier || "gold_plus"} · ${params.patch || "7"} 天`;
  ui.constraintBadge.textContent = source.built_sets_tab || "Actually Built Sets: 5";

  renderTeam(ui.allyTeam, data.ally_team || [], active.champion_slug || "");
  renderTeam(ui.enemyTeam, data.enemy_team || []);
  const notes = data.composition_notes || [];
  ui.compositionNotes.hidden = !notes.length;
  ui.compositionNotes.textContent = notes.join(" · ");
  renderDamageAnalysis(data.damage_analysis, data.build?.defensive_options || []);
  renderBoots(data.build?.boot_options || []);
  renderRoutes(data.build?.routes || []);
}

async function loadRecommendation() {
  const payload = await fetchJson("/api/recommendation");
  const data = payload.data;
  state.lastRevision = data?.session?.revision || null;
  renderRecommendation(data);
}

function renderHistory() {
  ui.historyList.replaceChildren();
  const feedbackCount = state.history.reduce((total, match) => total + (match.feedback?.length || 0), 0);
  ui.historySummary.textContent = `${state.history.length} 場 · ${feedbackCount} 筆套路回饋`;
  if (!state.history.length) {
    ui.historyList.append(element("div", "empty", "尚無歷史方案"));
    return;
  }
  for (const entry of state.history) {
    const row = element("article", "history-entry");
    const identity = element("div");
    identity.append(element("strong", "", entry.champion), element("span", "muted", fmtDate(entry.generated_at)));
    const allies = (entry.allies || []).map((player) => player.champion || player.slug).join("、");
    const enemies = (entry.enemies || []).map((player) => player.champion || player.slug).join("、");
    const teams = element("div", "history-teams", `我方 ${allies || "-"}\n敵方 ${enemies || "-"}`);
    teams.style.whiteSpace = "pre-line";
    const selectedRoutes = (entry.feedback || []).map((feedback) => `${feedback.sentiment > 0 ? "適合" : "不適合"}：${feedback.label}`).join(" · ");
    const routeInfo = element("div", "history-routes", selectedRoutes || (entry.routes || []).map((route) => route.label).join(" · "));
    const outcome = element("div", "outcome-control");
    const win = element("button", `win ${entry.outcome === 1 ? "selected" : ""}`.trim(), "勝");
    const loss = element("button", `loss ${entry.outcome === -1 ? "selected" : ""}`.trim(), "敗");
    win.type = loss.type = "button";
    win.addEventListener("click", () => saveOutcome(entry.match_key, entry.outcome === 1 ? null : 1).catch(showError));
    loss.addEventListener("click", () => saveOutcome(entry.match_key, entry.outcome === -1 ? null : -1).catch(showError));
    outcome.append(win, loss);
    row.append(identity, teams, routeInfo, outcome);
    ui.historyList.append(row);
  }
}

async function saveOutcome(matchKey, outcome) {
  await postJson("/api/outcome", { match_key: matchKey, outcome });
  await loadHistory();
  setStatus("已更新對局結果", "ok");
}

async function loadHistory() {
  const payload = await fetchJson("/api/history?limit=50");
  state.history = payload.history || [];
  renderHistory();
  if (state.recommendation) renderRoutes(state.recommendation.build?.routes || []);
}

function healthCell(label, value, detail) {
  const cell = element("div", "health-cell");
  cell.append(element("span", "eyebrow", label), element("strong", "", value));
  if (detail) cell.append(element("p", "", detail));
  return cell;
}

function renderHealth() {
  ui.healthGrid.replaceChildren();
  const health = state.health || {};
  const itemMap = health.item_map || {};
  const cache = health.cache || {};
  const history = health.history || {};
  const service = state.service || {};
  ui.healthGrid.append(
    healthCell("背景偵測", service.service_mode === "watch" ? "自動" : "手動", service.message || "-"),
    healthCell("Data Dragon", itemMap.ddragon_version || "-", `${fmtInt(itemMap.item_count)} 件裝備 · ${fmtInt(itemMap.champion_count)} 位英雄`),
    healthCell("LoLalytics 快取", `${fmtInt(cache.json_files)} 份`, fmtBytes(cache.size_bytes)),
    healthCell("本機學習", `${fmtInt(history.feedback)} 筆回饋`, `${fmtInt(history.recommendations)} 場 · ${fmtInt(history.wins)} 勝 · ${fmtInt(history.losses)} 敗`),
  );
}

async function loadHealth() {
  const payload = await fetchJson("/api/health");
  state.health = payload.health || {};
  renderHealth();
}

function renderServiceStatus(status) {
  state.service = status || {};
  const serviceState = status?.state || "offline";
  ui.serviceDot.className = `service-dot ${serviceState}`;
  ui.serviceState.textContent = status?.message || "背景服務尚未啟動";
  const type = serviceState === "error" ? "error" : ["detected", "preparing", "starting"].includes(serviceState) ? "busy" : ["ready", "waiting"].includes(serviceState) ? "ok" : "";
  setStatus(status?.last_error && serviceState === "error" ? `${status.message}：${status.last_error}` : status?.message || "", type);
  const shownMatch = state.recommendation?.session?.match_key;
  const pendingMatch = status?.current_match_key;
  if (["detected", "preparing"].includes(serviceState) && pendingMatch && pendingMatch !== shownMatch) {
    ui.emptyState.hidden = false;
    ui.emptyState.querySelector("strong").textContent = "正在準備本場方案";
    ui.emptyState.querySelector("span").textContent = "賽前聚合資料處理中。";
    ui.content.hidden = true;
  }
  renderHealth();
}

async function pollStatus() {
  if (state.polling) return;
  state.polling = true;
  try {
    const payload = await fetchJson("/api/status");
    const status = payload.status || {};
    renderServiceStatus(status);
    const revision = status.recommendation_revision;
    if (revision && revision !== state.lastRevision) {
      await Promise.all([loadRecommendation(), loadHistory(), loadHealth()]);
      showView("recommendation");
    }
  } catch (error) {
    ui.serviceDot.className = "service-dot offline";
    ui.serviceState.textContent = "無法連線背景服務";
  } finally {
    state.polling = false;
  }
}

async function loadSnapshots() {
  const payload = await fetchJson("/api/snapshots");
  ui.snapshotSelect.replaceChildren();
  for (const snapshot of payload.snapshots || []) {
    const option = element("option", "", snapshot.name);
    option.value = snapshot.path;
    ui.snapshotSelect.append(option);
  }
  ui.snapshotButton.disabled = !ui.snapshotSelect.options.length;
}

async function runManual(url, body) {
  ui.refreshButton.disabled = true;
  ui.snapshotButton.disabled = true;
  setStatus("正在產生賽前靜態方案", "busy");
  try {
    const payload = await postJson(url, body);
    state.lastRevision = payload.data?.session?.revision || null;
    renderRecommendation(payload.data);
    await Promise.all([loadSnapshots(), loadHistory(), loadHealth()]);
    showView("recommendation");
    setStatus("本場靜態方案已凍結", "ok");
    document.querySelector(".manual-menu").removeAttribute("open");
  } catch (error) {
    showError(error);
  } finally {
    ui.refreshButton.disabled = false;
    ui.snapshotButton.disabled = !ui.snapshotSelect.options.length;
  }
}

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => showView(tab.dataset.view));
}
ui.refreshButton.addEventListener("click", () => runManual("/api/recommend-live", {}));
ui.snapshotButton.addEventListener("click", () => runManual("/api/recommend-snapshot", { snapshot: ui.snapshotSelect.value }));
ui.healthRefresh.addEventListener("click", () => Promise.all([loadHealth(), pollStatus()]).catch(showError));
ui.activePortrait.addEventListener("error", () => {
  ui.activePortrait.style.visibility = "hidden";
});

async function initialize() {
  try {
    await loadHealth();
    await Promise.all([loadRecommendation(), loadSnapshots(), loadHistory()]);
    await pollStatus();
  } catch (error) {
    showError(error);
  }
  window.setInterval(pollStatus, 2500);
}

initialize();
