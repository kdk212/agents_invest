(() => {
  const load = async (u) => { try { const r = await fetch(u, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; } };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const num = (v, d = 2) => Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "-";
  const price = (v) => Number.isFinite(Number(v)) && Number(v) > 0 ? Math.round(Number(v)).toLocaleString("ko-KR") : "-";
  const hiddenLabels = new Set(["AI WIN 전일종가 모멘텀 상위주", "AI WIN 일간 추천 후보"]);
  let state = null;
  let rendering = false;

  function scrubRepeatedLabels(root = document) {
    root.querySelectorAll(".candidate-main small").forEach((node) => {
      if (hiddenLabels.has(node.textContent.trim())) node.remove();
    });
  }

  function rows(item) {
    const sections = item?.sections || {};
    return Object.entries(sections).flatMap(([section, values]) => Array.isArray(values) ? values.map((x) => ({ ...x, section })) : []);
  }

  function aiWinScore(x) {
    const rawScore = Number(x?.ai_win_score);
    const fallbackScore = Number(x?.adaptive_profit_score ?? x?.profit_score ?? x?.ai_win_score_100);
    return Number.isFinite(rawScore) ? rawScore : fallbackScore;
  }

  function card(x) {
    const score = num(aiWinScore(x), 2);
    const previousScore = num(x.previous_ai_win_score, 2);
    const previousClose = price(x.previous_close_price ?? x.signal_price ?? x.current_price);
    const stop = `${num(x.stop_loss_pct, 2)}% / ${price(x.stop_loss_price)}`;
    const target = `${num(x.target_return_pct ?? x.take_profit_trigger_pct, 2)}% / ${price(x.target_price)}`;
    const reason = x.recommendation_reason ? `<small class="candidate-reason">${esc(x.recommendation_reason)}</small>` : "";
    const risk = x.risk_note ? `<small class="candidate-risk">${esc(x.risk_note)}</small>` : "";
    return `<article class="candidate-card"><div class="candidate-main"><span class="candidate-code">${esc(x.code)}</span><strong>${esc(x.name)}</strong><small>${esc(x.entry_plan || x.buy_at || "시초가 진입")}</small>${reason}${risk}</div><div class="candidate-score"><span>AI WIN 원점수</span><strong>${esc(score)}</strong><small>전일 ${esc(previousScore)}</small></div><dl class="candidate-facts"><div><dt>전일종가</dt><dd>${esc(previousClose)}</dd></div><div><dt>등락</dt><dd>${esc(num(x.change_rate,2))}%</dd></div><div><dt>손절</dt><dd>${esc(stop)}</dd></div><div><dt>목표</dt><dd>${esc(target)}</dd></div></dl></article>`;
  }

  function withPreviousScores(items, item, index) {
    const previousItem = items[index + 1];
    const previousByCode = new Map(rows(previousItem).map((x) => [String(x.code), aiWinScore(x)]));
    return rows(item).map((x) => ({ ...x, previous_ai_win_score: previousByCode.get(String(x.code)) }));
  }

  function show(index) {
    if (!state) return;
    const { items, root, tabRoot } = state;
    const item = items[index] || items[0];
    rendering = true;
    tabRoot.querySelectorAll("[data-history-index]").forEach((button) => button.classList.toggle("active", Number(button.dataset.historyIndex) === index));
    const meta = document.getElementById("prismResultMeta");
    if (meta) meta.textContent = `${item.metadata?.signal_at || item.date} 기준 · ${item.metadata?.buy_at || item.date + " 시초가"} 진입 · AI WIN 원점수, 전일 점수, 선정 사유 표시`;
    const list = withPreviousScores(items, item, index);
    root.innerHTML = list.length ? list.map(card).join("") : '<div class="empty-state">추천 후보 대기</div>';
    scrubRepeatedLabels(root);
    state.activeIndex = index;
    requestAnimationFrame(() => { rendering = false; });
  }

  async function render() {
    const root = document.getElementById("candidateList");
    const tabRoot = document.querySelector(".result-tabs");
    if (!root || !tabRoot) return;
    const history = await load("./recommendation_history.json");
    const items = (history?.items || []).slice(-10).reverse();

    const observer = new MutationObserver(() => {
      scrubRepeatedLabels(root);
      if (rendering || !state) return;
      if (!state.root.querySelector(".candidate-card .candidate-score small")) {
        setTimeout(() => show(state.activeIndex || 0), 0);
      }
    });
    observer.observe(root, { childList: true, subtree: true });
    scrubRepeatedLabels(root);

    if (!items.length) return;

    state = { items, root, tabRoot, activeIndex: 0 };
    tabRoot.innerHTML = items.map((item, i) => `<button type="button" class="tab ${i === 0 ? "active" : ""}" data-history-index="${i}">${esc(item.date)}</button>`).join("");
    tabRoot.querySelectorAll("[data-history-index]").forEach((button) => button.addEventListener("click", () => show(Number(button.dataset.historyIndex))));
    show(0);
    setTimeout(() => show(state.activeIndex || 0), 300);
    setTimeout(() => show(state.activeIndex || 0), 900);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render); else render();
})();
