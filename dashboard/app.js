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
    { title: "보완 모듈 준비", detail: "수익 점수화, 리스크 차단, 성과 피드백 코드 준비", state: "done" },
    { title: "AWS Session Manager 복구", detail: "EC2 접속 후 설치 명령 실행", state: "warning" },
    { title: "PRISM 원본 통합", detail: "EC2에서 import_prism_runtime 실행 필요", state: "warning" },
    { title: "paper 검증", detail: "최소 거래 수와 검증 기준 충족 필요", state: "warning" },
    { title: "live 전환", detail: "모든 안전 조건 통과 전까지 금지", state: "blocked" }
  ],
  safety_checks: [
    { title: "Kill Switch", detail: "SSM에서 즉시 신규 실행 차단 가능", state: "warning" },
    { title: "RiskGovernor", detail: "주문 직전 포지션/손실/시장 리스크 차단", state: "done" },
    { title: "비밀값", detail: "OpenAI/KIS/Telegram SecureString 저장 필요", state: "warning" },
    { title: "Telegram", detail: "알림 수신 확인 필요", state: "warning" }
  ],
  feedback: {
    trigger_edge: "대기",
    sector_edge: "대기",
    ticker_edge: "대기"
  },
  next_actions: [
    {
      title: "EC2 명령 실행",
      detail: "PRISM 원본 가져오기, 비밀값 입력, 서비스 시작",
      url: "https://github.com/kdk212/agents_invest/blob/main/docs/EC2_COMMANDS_QUICK_HELP_ko.md"
    },
    {
      title: "비밀값 입력",
      detail: "OpenAI, KIS, Telegram 값을 SSM SecureString에 저장",
      url: "https://github.com/kdk212/agents_invest/blob/main/docs/RUNTIME_SECRET_INPUT_ko.md"
    }
  ]
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

function renderNextActions(items) {
  const root = document.getElementById("nextActions");
  if (!root) return;
  root.innerHTML = "";
  for (const item of items || []) {
    const action = document.createElement("a");
    action.className = "next-action";
    action.href = item.url || "#";
    action.target = "_blank";
    action.rel = "noreferrer";
    const title = document.createElement("strong");
    title.textContent = item.title || "-";
    const detail = document.createElement("span");
    detail.textContent = item.detail || "";
    action.append(title, detail);
    root.appendChild(action);
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

function renderLatestCandidates() {
  const root = document.getElementById("candidateList");
  if (!root) return;

  const result = latestResults[activeResultMode];
  const candidates = flattenCandidates(result).slice(0, 8);
  const meta = result?.metadata;
  setText(
    "prismResultMeta",
    meta ? `${labelForMode(meta.trigger_mode || activeResultMode)} · 기준일 ${meta.trade_date || "-"}` : "실행 결과 대기"
  );

  root.innerHTML = "";
  if (!candidates.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "아직 표시할 PRISM 후보가 없습니다. EC2 서비스가 한 번 실행되면 여기에 결과가 나타납니다.";
    root.appendChild(empty);
    return;
  }

  for (const candidate of candidates) {
    const card = document.createElement("article");
    card.className = "candidate-card";
    const score = numberText(candidate.profit_score ?? candidate.final_score ?? candidate.agent_fit_score, 2);
    const change = numberText(candidate.change_rate, 2);
    card.innerHTML = `
      <div class="candidate-main">
        <span class="candidate-code">${escapeHtml(candidate.code || "-")}</span>
        <strong>${escapeHtml(candidate.name || "이름 없음")}</strong>
        <small>${escapeHtml(candidate.trigger_type || "PRISM 후보")}</small>
      </div>
      <div class="candidate-score">
        <span>점수</span>
        <strong>${escapeHtml(score)}</strong>
      </div>
      <dl class="candidate-facts">
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
  return rows.sort((a, b) => (b.profit_score ?? b.final_score ?? 0) - (a.profit_score ?? a.final_score ?? 0));
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
    status.integration_state === "완료" ? 1 : 0.35,
    status.validation_state === "통과" ? 1 : 0.25,
    status.kill_switch === "OFF" ? 1 : 0.3,
    status.trading_mode === "paper" ? 0.75 : 0.45,
  ];
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#eef3f1";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#d9e0dc";
  for (let x = 24; x < canvas.width; x += 32) {
    ctx.beginPath(); ctx.moveTo(x, 18); ctx.lineTo(x, canvas.height - 18); ctx.stroke();
  }
  const colors = ["#3267a8", "#287c61", "#b37513", "#17201d"];
  states.forEach((value, index) => {
    const x = 44 + index * 72;
    const height = 118 * value;
    ctx.fillStyle = colors[index];
    ctx.fillRect(x, 146 - height, 38, height);
    ctx.fillStyle = "#62706c";
    ctx.font = "12px system-ui";
    ctx.fillText(["통합", "검증", "정지", "운영"][index], x - 2, 166);
  });
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
  renderList("timeline", status.timeline);
  renderList("safetyChecks", [runtimeCheck(status.runtime), ...(status.safety_checks || [])]);
  renderNextActions(status.next_actions);
  renderFeedback(status.feedback);
  renderLatestCandidates();
  drawStatusCanvas(status);
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

wireResultTabs();
Promise.all([loadStatus(), loadRuntimeStatus(), loadLatestResults()]).then(([status, runtime, results]) => {
  latestResults = results;
  render({ ...status, runtime });
});