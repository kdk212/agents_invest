const fallbackStatus = {
  updated_at: "대시보드 배포 후 status.json 대기 중",
  overall: "warning",
  trading_mode: "paper",
  mode_detail: "초기 운영은 paper 모드 권장",
  integration_state: "대기",
  integration_detail: "EC2에서 PRISM 원본 가져오기 필요",
  kill_switch: "확인 필요",
  kill_switch_detail: "/agents-invest/kill-switch 확인",
  validation_state: "미검증",
  validation_detail: "PaperTradingValidator 통과 전 live 금지",
  timeline: [
    { title: "PRISM 추천 생성", detail: "오전/오후 후보 생성", state: "done" },
    { title: "백테스트 보완", detail: "2년/18개월/1년 구간 최적화", state: "running" },
    { title: "paper 포트폴리오", detail: "추천 누적 비중과 매도 신호 추적", state: "running" },
    { title: "live 전환", detail: "모든 안전 조건 통과 전까지 금지", state: "blocked" }
  ],
  safety_checks: [
    { title: "Kill Switch", detail: "SSM/env에서 즉시 신규 실행 차단 가능", state: "warning" },
    { title: "RiskGovernor", detail: "주문 직전 포지션/손실/시장 리스크 차단", state: "done" },
    { title: "Telegram", detail: "알림 수신 확인 필요", state: "warning" }
  ],
  feedback: {
    trigger_edge: "대기",
    sector_edge: "대기",
    ticker_edge: "대기"
  },
  next_actions: []
};

const resultFiles = {
  morning: "./prism_latest_morning.json",
  afternoon: "./prism_latest_afternoon.json",
};
let latestResults = { morning: null, afternoon: null };
let activeResultMode = "morning";

async function loadStatus() {
  try {
    const response = await fetch("./status.json", { cache: "no-store" });
    if (!response.ok) throw new Error("status.json not found");
    return { ...fallbackStatus, ...(await response.json()) };
  } catch (_error) {
    return fallbackStatus;
  }
}

async function loadJsonOrNull(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    return await response.json();
  } catch (_error) {
    return null;
  }
}

async function loadRuntimeStatus() {
  return await loadJsonOrNull("./runtime_status.json");
}

async function loadPortfolioStatus() {
  return await loadJsonOrNull("./portfolio_status.json");
}

async function loadAdaptiveStrategy() {
  return await loadJsonOrNull("./adaptive_strategy.json");
}

async function loadLatestResults() {
  const entries = await Promise.all(
    Object.entries(resultFiles).map(async ([mode, url]) => [mode, await loadJsonOrNull(url)])
  );
  return Object.fromEntries(entries);
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value ?? "-";
}

function renderList(id, items) {
  const root = document.getElementById(id);
  if (!root) return;
  root.innerHTML = "";
  for (const item of items || []) {
    const li = document.createElement("li");
    const dot = document.createElement("span");
    dot.className = `status-dot ${item.state || "warning"}`;
    const body = document.createElement("span");
    const title = document.createElement("span");
    title.className = "item-title";
    title.textContent = item.title || "-";
    const detail = document.createElement("span");
    detail.className = "item-detail";
    detail.textContent = item.detail || "";
    body.append(title, detail);
    li.append(dot, body);
    root.appendChild(li);
  }
}

function renderFeedback(feedback) {
  const root = document.getElementById("feedbackGrid");
  if (!root) return;
  const cards = [
    ["트리거", feedback?.trigger_edge ?? "대기", "과거 트리거 성과"],
    ["섹터", feedback?.sector_edge ?? "대기", "섹터별 평균 성과"],
    ["종목", feedback?.ticker_edge ?? "대기", "반복 손실/성과"],
  ];
  root.innerHTML = "";
  for (const [label, value, detail] of cards) {
    const card = document.createElement("div");
    card.className = "feedback-card";
    card.innerHTML = `<span class="label">${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small>`;
    root.appendChild(card);
  }
}

function renderPortfolio(portfolio) {
  const summary = portfolio?.summary || {};
  setText("portfolioReturn", summary.total_return_pct || "0.00%");
  setText("portfolioAnnualized", summary.annualized_return_pct || "0.00%");
  setText("portfolioReturnDetail", `시작일 ${portfolio?.start_date || "2026-06-01"} · 추천 ${portfolio?.recommendation_count || 0}건`);
  setText("openUnits", `${summary.open_units ?? 0}`);
  setText("openPositions", `보유 종목 ${summary.open_positions ?? 0}`);
  setText("portfolioUpdatedAt", portfolio?.updated_at ? `갱신 ${portfolio.updated_at}` : "포트폴리오 결과 대기");
  renderHoldings(portfolio?.holdings || []);
  renderSellSignals(portfolio?.sell_signals || []);
  drawPortfolioCanvas(portfolio?.equity_curve || []);
}

function renderAdaptiveStrategy(strategy) {
  const best = strategy?.best_summary || {};
  setText("backtestCagr", pctText(best.cagr));
  setText("backtestPeriod", best.period_months ? `최근 ${best.period_months}개월 · ${best.start || "-"}~${best.end || "-"}` : "최적화 결과 대기");
  setText("strategySource", strategy?.source || "기본 설정");
  setText("strategyPeriod", strategy?.selected_period_months ? `${strategy.selected_period_months}개월` : "-");
  setText("strategyThreshold", numberText(strategy?.score_threshold, 2));
  setText("strategyStop", numberText(strategy?.stop_multiplier, 2));
  const trigger = pctText(strategy?.take_profit_trigger_pct);
  const trail = pctText(strategy?.take_profit_trailing_pct);
  setText("strategyTakeProfit", `${trigger} / ${trail}`);
}

function renderHoldings(holdings) {
  const root = document.getElementById("holdingList");
  if (!root) return;
  root.innerHTML = "";
  if (!holdings.length) {
    root.appendChild(emptyNode("아직 보유 포트폴리오가 없습니다. 2026-06-01 이후 추천 기록이 쌓이면 표시됩니다."));
    return;
  }
  for (const item of holdings.slice(0, 12)) {
    const row = document.createElement("article");
    row.className = "holding-row";
    row.innerHTML = `
      <div>
        <span class="candidate-code">${escapeHtml(item.ticker || "-")}</span>
        <strong>${escapeHtml(item.company_name || "-")}</strong>
        <small>최근 추천 ${escapeHtml(item.last_signal_date || "-")}</small>
      </div>
      <dl>
        <div><dt>비중</dt><dd>${escapeHtml(item.weight_units ?? 0)}</dd></div>
        <div><dt>수익률</dt><dd class="${pctClass(item.return_pct)}">${escapeHtml(item.return_pct || "0.00%")}</dd></div>
        <div><dt>현재가</dt><dd>${escapeHtml(priceText(item.current_price))}</dd></div>
        <div><dt>손절/목표</dt><dd>${escapeHtml(priceText(item.avg_stop))} / ${escapeHtml(priceText(item.avg_target))}</dd></div>
      </dl>
    `;
    root.appendChild(row);
  }
}

function renderSellSignals(signals) {
  const root = document.getElementById("sellSignalList");
  if (!root) return;
  root.innerHTML = "";
  if (!signals.length) {
    root.appendChild(emptyNode("아직 매도 신호가 없습니다."));
    return;
  }
  for (const item of signals.slice(0, 10)) {
    const row = document.createElement("article");
    row.className = "sell-row";
    row.innerHTML = `
      <div>
        <span>${escapeHtml(item.date || "-")}</span>
        <strong>${escapeHtml(item.company_name || item.ticker || "-")}</strong>
        <small>${escapeHtml(item.reason || "sell")}</small>
      </div>
      <div class="sell-result ${pctClass(item.realized_return_pct)}">
        ${escapeHtml(item.realized_return_pct || "0.00%")}
      </div>
    `;
    root.appendChild(row);
  }
}

function renderLatestCandidates() {
  const root = document.getElementById("candidateList");
  if (!root) return;

  const result = latestResults[activeResultMode];
  const candidates = flattenCandidates(result).slice(0, 8);
  const meta = result?.metadata;
  const adaptive = meta?.adaptive_strategy;
  const suffix = adaptive?.status === "enhanced" ? ` · 보완 ${adaptive.enhanced_count || 0}건` : "";
  setText(
    "prismResultMeta",
    meta ? `${labelForMode(meta.trigger_mode || activeResultMode)} · 기준일 ${meta.trade_date || "-"}${suffix}` : "실행 결과 대기"
  );

  root.innerHTML = "";
  if (!candidates.length) {
    root.appendChild(emptyNode("아직 표시할 PRISM 후보가 없습니다."));
    return;
  }

  for (const candidate of candidates) {
    const card = document.createElement("article");
    card.className = "candidate-card";
    const score = numberText(candidate.adaptive_profit_score ?? candidate.profit_score ?? candidate.final_score ?? candidate.agent_fit_score, 2);
    const aiScore = numberText(candidate.ai_win_score_100, 1);
    const change = numberText(candidate.change_rate, 2);
    card.innerHTML = `
      <div class="candidate-main">
        <span class="candidate-code">${escapeHtml(candidate.code || "-")}</span>
        <strong>${escapeHtml(candidate.name || "이름 없음")}</strong>
        <small>${escapeHtml(candidate.trigger_type || "PRISM 후보")}</small>
      </div>
      <div class="candidate-score">
        <span>보완점수</span>
        <strong>${escapeHtml(score)}</strong>
      </div>
      <dl class="candidate-facts">
        <div><dt>AI WIN</dt><dd>${escapeHtml(aiScore)}</dd></div>
        <div><dt>등락</dt><dd>${escapeHtml(change)}%</dd></div>
        <div><dt>손절</dt><dd>${escapeHtml(numberText(candidate.stop_loss_pct, 2))}%</dd></div>
        <div><dt>목표</dt><dd>${escapeHtml(priceText(candidate.target_price))}</dd></div>
      </dl>
    `;
    root.appendChild(card);
  }
}

function flattenCandidates(result) {
  if (!result || typeof result !== "object") return [];
  const rows = [];
  for (const [triggerType, value] of Object.entries(result)) {
    if (triggerType === "metadata" || !Array.isArray(value)) continue;
    for (const item of value) {
      rows.push({ ...item, trigger_type: triggerType });
    }
  }
  return rows.sort((a, b) => (b.adaptive_profit_score ?? b.profit_score ?? b.final_score ?? 0) - (a.adaptive_profit_score ?? a.profit_score ?? a.final_score ?? 0));
}

function wireResultTabs() {
  document.querySelectorAll("[data-result-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      activeResultMode = button.dataset.resultMode || "morning";
      document.querySelectorAll("[data-result-mode]").forEach((node) => {
        node.classList.toggle("active", node === button);
      });
      renderLatestCandidates();
    });
  });
}

function drawStatusCanvas(status) {
  const canvas = document.getElementById("statusCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const states = [
    status.portfolio?.summary?.open_positions ? 0.9 : 0.35,
    status.strategy?.best_summary?.cagr ? 0.85 : 0.3,
    status.runtime?.runtime_ready ? 0.9 : 0.35,
    status.trading_mode === "paper" ? 0.75 : 0.45,
  ];
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
  gradient.addColorStop(0, "#f7faf8");
  gradient.addColorStop(1, "#e8f0ed");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#d9e0dc";
  for (let x = 24; x < canvas.width; x += 32) {
    ctx.beginPath(); ctx.moveTo(x, 18); ctx.lineTo(x, canvas.height - 18); ctx.stroke();
  }
  const colors = ["#287c61", "#3267a8", "#b37513", "#17201d"];
  states.forEach((value, index) => {
    const x = 42 + index * 72;
    const height = 118 * value;
    ctx.fillStyle = colors[index];
    ctx.fillRect(x, 146 - height, 40, height);
    ctx.fillStyle = "#62706c";
    ctx.font = "12px system-ui";
    ctx.fillText(["포트", "백테", "런타임", "운영"][index], x - 1, 166);
  });
}

function drawPortfolioCanvas(curve) {
  const canvas = document.getElementById("portfolioCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#d9e0dc";
  ctx.lineWidth = 1;
  for (let y = 34; y < canvas.height - 28; y += 42) {
    ctx.beginPath(); ctx.moveTo(34, y); ctx.lineTo(canvas.width - 18, y); ctx.stroke();
  }
  if (!curve.length) {
    ctx.fillStyle = "#62706c";
    ctx.font = "15px system-ui";
    ctx.fillText("포트폴리오 수익률 데이터 대기", 34, 130);
    return;
  }
  const values = curve.map((row) => parsePct(row.return_pct));
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0.01);
  const range = max - min || 0.01;
  const left = 38, right = canvas.width - 22, top = 24, bottom = canvas.height - 34;
  ctx.strokeStyle = "#287c61";
  ctx.lineWidth = 3;
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = left + ((right - left) * index) / Math.max(values.length - 1, 1);
    const y = bottom - ((value - min) / range) * (bottom - top);
    if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#17201d";
  ctx.font = "13px system-ui";
  ctx.fillText(`최저 ${formatPct(min)} · 최고 ${formatPct(max)}`, left, 18);
  ctx.fillText(curve[curve.length - 1]?.date || "", left, canvas.height - 10);
}

function runtimeCheck(runtime) {
  if (!runtime) {
    return { title: "서비스 상태", detail: "runtime_status.json 대기", state: "warning" };
  }
  const status = runtime.status || "unknown";
  const updated = runtime.updated_at || "-";
  const missing = Array.isArray(runtime.missing_secret_names) ? runtime.missing_secret_names.length : 0;
  const state = status.includes("failed") || status.includes("blocked") ? "blocked" : runtime.runtime_ready ? "done" : "warning";
  const detail = missing
    ? `${status} · 비밀값 ${missing}개 대기 · ${updated}`
    : `${status} · ${updated}`;
  return { title: "서비스 상태", detail, state };
}

function render(status) {
  setText("tradingMode", status.trading_mode || "-");
  setText("modeDetail", status.mode_detail || "-");
  setText("integrationState", status.integration_state || "-");
  setText("integrationDetail", status.integration_detail || "-");
  setText("killSwitch", status.kill_switch || "-");
  setText("killSwitchDetail", status.kill_switch_detail || "-");
  setText("validationState", status.validation_state || "-");
  setText("validationDetail", status.validation_detail || "-");
  setText("updatedAt", status.runtime?.updated_at || status.updated_at || "-");
  const runtimeText = status.runtime?.status ? `서비스 ${status.runtime.status}` : null;
  setText("overallText", runtimeText || (status.overall === "ok" ? "운영 가능 상태" : status.overall === "blocked" ? "차단 상태" : "확인 필요"));
  const pulse = document.getElementById("overallPulse");
  if (pulse) pulse.className = `pulse ${status.overall || "warning"}`;
  renderPortfolio(status.portfolio);
  renderAdaptiveStrategy(status.strategy);
  renderList("timeline", status.timeline);
  renderList("safetyChecks", [runtimeCheck(status.runtime), ...(status.safety_checks || [])]);
  renderFeedback(status.feedback);
  renderLatestCandidates();
  drawStatusCanvas(status);
}

function emptyNode(text) {
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}

function labelForMode(mode) {
  return mode === "morning" ? "오전" : mode === "afternoon" ? "오후" : mode || "-";
}

function numberText(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(digits);
}

function priceText(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "-";
  return Math.round(number).toLocaleString("ko-KR");
}

function pctText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(2)}%`;
}

function parsePct(value) {
  const number = Number(String(value ?? "0").replace("%", ""));
  return Number.isFinite(number) ? number / 100 : 0;
}

function formatPct(value) {
  return `${(value * 100).toFixed(2)}%`;
}

function pctClass(value) {
  const parsed = parsePct(value);
  return parsed > 0 ? "positive" : parsed < 0 ? "negative" : "flat";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

wireResultTabs();
Promise.all([
  loadStatus(),
  loadRuntimeStatus(),
  loadLatestResults(),
  loadPortfolioStatus(),
  loadAdaptiveStrategy(),
]).then(([status, runtime, results, portfolio, strategy]) => {
  latestResults = results;
  render({ ...status, runtime, portfolio, strategy });
});