(() => {
  const genericLabels = new Set([
    "AI WIN 전일종가 모멘텀 상위주",
    "AI WIN 일간 추천 후보",
    "추천 후보",
    "PRISM 후보",
  ]);

  const safeText = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const numberTextLocal = (value, digits = 2) => {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "-";
  };

  const priceTextLocal = (value) => {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.round(number).toLocaleString("ko-KR") : "-";
  };

  const cleanLabel = (value) => {
    const text = String(value ?? "").trim();
    return text && !genericLabels.has(text) ? text : "";
  };

  const candidateReason = (candidate) => {
    const reason = cleanLabel(candidate.recommendation_reason);
    if (reason) return reason;
    const components = candidate.score_components || {};
    const parts = [];
    if (Number.isFinite(Number(components.mom60_pct))) parts.push(`60일 ${Number(components.mom60_pct).toFixed(1)}%`);
    if (Number.isFinite(Number(components.mom120_pct))) parts.push(`120일 ${Number(components.mom120_pct).toFixed(1)}%`);
    if (Number.isFinite(Number(components.turnover_change_pct))) parts.push(`거래대금 ${Number(components.turnover_change_pct).toFixed(1)}%`);
    return parts.length ? parts.slice(0, 3).join(" · ") : "선정 사유 기록 없음";
  };

  const candidateRisk = (candidate) => cleanLabel(candidate.risk_note);

  const flatten = (result) => {
    if (!result || typeof result !== "object") return [];
    const rows = [];
    for (const [sectionName, value] of Object.entries(result)) {
      if (sectionName === "metadata" || !Array.isArray(value)) continue;
      for (const item of value) rows.push({ ...item, section_name: sectionName });
    }
    return rows.sort((a, b) => (b.adaptive_profit_score ?? b.profit_score ?? b.final_score ?? b.ai_win_score ?? 0) - (a.adaptive_profit_score ?? a.profit_score ?? a.final_score ?? a.ai_win_score ?? 0));
  };

  window.renderLatestCandidates = function patchedRenderLatestCandidates() {
    const root = document.getElementById("candidateList");
    if (!root) return;

    const result = latestResults?.[activeResultMode];
    const candidates = flatten(result).slice(0, 8);
    const meta = result?.metadata;
    const policy = meta?.recommendation_policy ? ` · ${meta.recommendation_policy}` : "";
    setText(
      "prismResultMeta",
      meta ? `${meta.signal_at || meta.trade_date || "-"} 기준 · ${meta.buy_at || "다음 거래일 시초가"} 진입${policy}` : "실행 결과 대기"
    );

    root.innerHTML = "";
    if (!candidates.length) {
      root.appendChild(emptyNode("아직 표시할 추천 후보가 없습니다."));
      return;
    }

    for (const candidate of candidates) {
      const card = document.createElement("article");
      card.className = "candidate-card";
      const score = numberTextLocal(candidate.ai_win_score ?? candidate.adaptive_profit_score ?? candidate.profit_score ?? candidate.final_score, 2);
      const prevClose = priceTextLocal(candidate.previous_close_price ?? candidate.signal_price ?? candidate.current_price);
      const change = numberTextLocal(candidate.change_rate, 2);
      const stopPct = numberTextLocal(candidate.stop_loss_pct, 2);
      const stopPrice = priceTextLocal(candidate.stop_loss_price);
      const targetPct = numberTextLocal(candidate.target_return_pct ?? candidate.take_profit_trigger_pct, 2);
      const targetPrice = priceTextLocal(candidate.target_price);
      const reason = candidateReason(candidate);
      const risk = candidateRisk(candidate);
      card.innerHTML = `
        <div class="candidate-main">
          <span class="candidate-code">${safeText(candidate.code || "-")}</span>
          <strong>${safeText(candidate.name || "이름 없음")}</strong>
          <small>${safeText(candidate.entry_plan || candidate.buy_at || "시초가 진입")}</small>
          <small class="candidate-reason">${safeText(reason)}</small>
          ${risk ? `<small class="candidate-risk">${safeText(risk)}</small>` : ""}
        </div>
        <div class="candidate-score">
          <span>AI WIN 원점수</span>
          <strong>${safeText(score)}</strong>
        </div>
        <dl class="candidate-facts">
          <div><dt>전일종가</dt><dd>${safeText(prevClose)}</dd></div>
          <div><dt>등락</dt><dd>${safeText(change)}%</dd></div>
          <div><dt>손절</dt><dd>${safeText(stopPct)}% / ${safeText(stopPrice)}</dd></div>
          <div><dt>목표</dt><dd>${safeText(targetPct)}% / ${safeText(targetPrice)}</dd></div>
        </dl>
      `;
      root.appendChild(card);
    }
  };
})();
