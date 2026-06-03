(() => {
  const resultFiles = {
    morning: "./prism_latest_morning.json",
    afternoon: "./prism_latest_afternoon.json",
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function loadJson(url) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) return null;
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  function text(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value ?? "-";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
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

  function labelForMode(mode) {
    return mode === "morning" ? "오전" : mode === "afternoon" ? "오후" : mode || "-";
  }

  function flattenCandidates(result) {
    if (!result || typeof result !== "object") return [];
    const rows = [];
    for (const [triggerType, value] of Object.entries(result)) {
      if (triggerType === "metadata" || !Array.isArray(value)) continue;
      for (const item of value) rows.push({ ...item, trigger_type: triggerType });
    }
    return rows.sort((a, b) => {
      const bScore = Number(b.ai_win_score_100 ?? b.adaptive_profit_score ?? b.profit_score ?? b.final_score ?? 0);
      const aScore = Number(a.ai_win_score_100 ?? a.adaptive_profit_score ?? a.profit_score ?? a.final_score ?? 0);
      return bScore - aScore;
    });
  }

  function renderAiWinFirst(result, mode) {
    const root = document.getElementById("candidateList");
    if (!root) return;
    const meta = result?.metadata || {};
    const adaptive = meta.adaptive_strategy || {};
    const candidates = flattenCandidates(result).slice(0, 8);
    const hasAiWin = candidates.some((item) => item.ai_win_score_100 !== undefined || item.adaptive_profit_score !== undefined);

    text(
      "prismResultMeta",
      meta.trade_date
        ? `${labelForMode(meta.trigger_mode || mode)} · 기준일 ${meta.trade_date} · ${hasAiWin ? "AI WIN 우선정렬" : "AI WIN 보정 대기"}`
        : "실행 결과 대기"
    );

    root.innerHTML = "";
    if (!candidates.length) {
      root.innerHTML = '<div class="empty-state">아직 표시할 추천 후보가 없습니다.</div>';
      return;
    }

    if (!hasAiWin) {
      const notice = document.createElement("div");
      notice.className = "empty-state ai-warning";
      notice.textContent = "현재 화면은 마지막 PRISM 원본 후보입니다. AI WIN 보정/백테스트가 성공하면 이 영역이 보정 점수 우선으로 바뀝니다.";
      root.appendChild(notice);
    }

    for (const candidate of candidates) {
      const card = document.createElement("article");
      card.className = "candidate-card";
      const aiScore = numberText(candidate.ai_win_score_100, 1);
      const adaptiveScore = numberText(candidate.adaptive_profit_score ?? candidate.profit_score ?? candidate.final_score, 2);
      const change = numberText(candidate.change_rate, 2);
      card.innerHTML = `
        <div class="candidate-main">
          <span class="candidate-code">${escapeHtml(candidate.code || "-")}</span>
          <strong>${escapeHtml(candidate.name || "이름 없음")}</strong>
          <small>${escapeHtml(candidate.trigger_type || "추천 후보")}</small>
        </div>
        <div class="candidate-score">
          <span>${candidate.ai_win_score_100 !== undefined ? "AI WIN" : "기존점수"}</span>
          <strong>${escapeHtml(candidate.ai_win_score_100 !== undefined ? aiScore : adaptiveScore)}</strong>
        </div>
        <dl class="candidate-facts">
          <div><dt>보완점수</dt><dd>${escapeHtml(adaptiveScore)}</dd></div>
          <div><dt>등락</dt><dd>${escapeHtml(change)}%</dd></div>
          <div><dt>손절</dt><dd>${escapeHtml(numberText(candidate.stop_loss_pct, 2))}%</dd></div>
          <div><dt>목표</dt><dd>${escapeHtml(priceText(candidate.target_price))}</dd></div>
        </dl>
      `;
      root.appendChild(card);
    }
  }

  function translatePaperLabels() {
    const replacements = new Map([
      ["paper", "모의운영"],
      ["paper 권장", "모의운영 권장"],
      ["paper 결과 기반", "모의운영 결과 기반"],
      ["paper 포트폴리오", "모의 포트폴리오"],
      ["live 전환", "실거래 전환"],
      ["live 차단 우선", "실거래 차단 우선"],
    ]);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      let value = node.nodeValue;
      for (const [from, to] of replacements.entries()) value = value.replaceAll(from, to);
      node.nodeValue = value;
    }
  }

  function renderRuntimeKorean(runtime) {
    const checks = document.getElementById("safetyChecks");
    if (!checks || !runtime) return;
    const first = checks.querySelector("li .item-detail");
    if (!first) return;
    const status = runtime.status || "unknown";
    const missing = Array.isArray(runtime.missing_secret_names) ? runtime.missing_secret_names : [];
    const importantMissing = missing.filter((name) => !name.startsWith("KIS_"));
    let label = status;
    if (status === "running_prism_batch") label = "추천주 계산 중";
    if (status === "prism_batch_cycle_failed") label = "추천주 갱신 실패";
    if (status === "prism_batch_cycle_complete") label = "추천주 갱신 완료";
    const missingText = importantMissing.length ? ` · 필수 비밀값 ${importantMissing.length}개 대기` : "";
    first.textContent = `${label}${missingText} · ${runtime.updated_at || "-"}`;
  }

  async function renderPatch() {
    await sleep(350);
    translatePaperLabels();
    const runtime = await loadJson("./runtime_status.json");
    renderRuntimeKorean(runtime);
    const active = document.querySelector("[data-result-mode].active")?.dataset?.resultMode || "morning";
    const result = await loadJson(resultFiles[active]);
    renderAiWinFirst(result, active);

    document.querySelectorAll("[data-result-mode]").forEach((button) => {
      button.addEventListener("click", async () => {
        await sleep(50);
        const mode = button.dataset.resultMode || "morning";
        renderAiWinFirst(await loadJson(resultFiles[mode]), mode);
        translatePaperLabels();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderPatch);
  } else {
    renderPatch();
  }
})();
