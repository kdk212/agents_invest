const fallbackStatus = {
  updated_at: "대시보드 배포 후 status.json 대기 중",
  overall: "warning",
  trading_mode: "paper",
  mode_detail: "초기 운영은 paper 모드 권장",
  integration_state: "대기",
  integration_detail: "GitHub Actions에서 integrate-prism-insight 실행 필요",
  kill_switch: "확인 필요",
  kill_switch_detail: "/agents-invest/kill-switch 확인",
  validation_state: "미검증",
  validation_detail: "PaperTradingValidator 통과 전 live 금지",
  timeline: [
    { title: "보완 모듈 준비", detail: "수익 점수화, 리스크 차단, 성과 피드백 코드 준비", state: "done" },
    { title: "PRISM 원본 통합", detail: "Actions에서 integrate-prism-insight 실행 필요", state: "warning" },
    { title: "paper 검증", detail: "최소 거래 수와 검증 기준 충족 필요", state: "warning" },
    { title: "AWS 24시간 운영", detail: "EC2 또는 GitHub Pages로 PC 없이 운영", state: "running" },
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
  }
};

async function loadStatus() {
  try {
    const response = await fetch("./status.json", { cache: "no-store" });
    if (!response.ok) throw new Error("status.json not found");
    return { ...fallbackStatus, ...(await response.json()) };
  } catch (_error) {
    return fallbackStatus;
  }
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
    card.innerHTML = `<span class="label">${label}</span><strong>${value}</strong><small>${detail}</small>`;
    root.appendChild(card);
  }
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

function render(status) {
  setText("tradingMode", status.trading_mode || "-");
  setText("modeDetail", status.mode_detail || "-");
  setText("integrationState", status.integration_state || "-");
  setText("integrationDetail", status.integration_detail || "-");
  setText("killSwitch", status.kill_switch || "-");
  setText("killSwitchDetail", status.kill_switch_detail || "-");
  setText("validationState", status.validation_state || "-");
  setText("validationDetail", status.validation_detail || "-");
  setText("updatedAt", status.updated_at || "-");
  setText("overallText", status.overall === "ok" ? "운영 가능 상태" : status.overall === "blocked" ? "차단 상태" : "확인 필요");
  const pulse = document.getElementById("overallPulse");
  if (pulse) pulse.className = `pulse ${status.overall || "warning"}`;
  renderList("timeline", status.timeline);
  renderList("safetyChecks", status.safety_checks);
  renderFeedback(status.feedback);
  drawStatusCanvas(status);
}

loadStatus().then(render);
